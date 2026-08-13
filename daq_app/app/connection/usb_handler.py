# usb_handler.py — Detección y lectura UART del ESP32-S3 (pyserial).
# Hilo Qt: escanea puertos, envía handshake 0xAA 0x55, espera ACK 0x55 0xAA
# y luego emite frames binarios parseados a 50 Hz.

import time

from PySide6.QtCore import QThread, Signal

from .protocol import Frame, FrameParser, HANDSHAKE, HANDSHAKE_ACK

_ESP32_VIDS = {0x303A, 0x10C4, 0x1A86, 0x0403}   # Espressif, CP210x, CH340, FTDI


def scan_ports() -> list[str]:
    """Puertos serie candidatos, priorizando VIDs conocidos de ESP32."""
    try:
        from serial.tools import list_ports
    except ImportError:
        return []
    known, others = [], []
    for p in list_ports.comports():
        (known if p.vid in _ESP32_VIDS else others).append(p.device)
    return known + others


class UsbHandler(QThread):
    frame_received = Signal(Frame)
    connected = Signal(str)          # nombre del puerto
    disconnected = Signal(str)       # motivo

    def __init__(self, port: str | None = None, baud: int = 115200, parent=None):
        super().__init__(parent)
        self._port = port
        self._baud = baud
        self._ser = None
        self._running = False
        self._tx_queue: list[bytes] = []

    # ── API pública ─────────────────────────────────────────────────────
    def send_command(self, data: bytes):
        self._tx_queue.append(data)

    def stop(self):
        self._running = False
        self.wait(2000)

    # ── Hilo ────────────────────────────────────────────────────────────
    def run(self):
        import serial

        ports = [self._port] if self._port else scan_ports()
        if not ports:
            self.disconnected.emit("Sin puertos serie disponibles")
            return

        self._running = True
        for port in ports:
            if not self._running:
                return
            try:
                ser = serial.Serial(port, self._baud, timeout=0.1)
            except (serial.SerialException, OSError):
                continue
            if self._handshake(ser):
                self._ser = ser
                self.connected.emit(port)
                self._read_loop(ser)
                return
            ser.close()

        self.disconnected.emit("Ningún ESP32-S3 respondió al handshake")

    def _handshake(self, ser) -> bool:
        """Envía 0xAA 0x55 y espera 0x55 0xAA (reintenta ~3 s)."""
        deadline = time.monotonic() + 3.0
        buf = b""
        while time.monotonic() < deadline and self._running:
            try:
                ser.reset_input_buffer()
                ser.write(HANDSHAKE)
                time.sleep(0.2)
                buf += ser.read(64)
            except (OSError, Exception):
                return False
            if HANDSHAKE_ACK in buf:
                return True
        return False

    def _read_loop(self, ser):
        parser = FrameParser()
        while self._running:
            try:
                while self._tx_queue:
                    ser.write(self._tx_queue.pop(0))
                data = ser.read(256)
            except (OSError, Exception) as e:
                self.disconnected.emit(f"USB desconectado: {e}")
                break
            for frame in parser.feed(data):
                self.frame_received.emit(frame)
        try:
            ser.close()
        except Exception:
            pass
        self._ser = None
