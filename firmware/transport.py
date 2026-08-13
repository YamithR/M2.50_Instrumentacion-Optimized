# transport.py — Capa de transporte: USB UART / BLE / ninguno.
# El host es el script Python (daq_app). El protocolo es binario:
#   device → host : frames de 14 bytes (ver protocol en README A.5)
#   host → device : comandos de 3 bytes (0xBB cmd arg)
#
# Modos: "none" | "usb" | "ble"

import sys
import select
import config

MODE_NONE = "none"
MODE_USB  = "usb"
MODE_BLE  = "ble"

_mode      = MODE_NONE
_poll      = None
_stdin_buf = b""
_rx_cmds   = []          # comandos parseados pendientes

# ── BLE (Nordic UART Service) ──────────────────────────────────────────────
_ble           = None
_ble_connected = False
_ble_conn      = None
_tx_handle     = None
_rx_handle     = None
_ble_rx_buf    = b""

_NUS_UUID    = "6E400001-B5A3-F393-E0A9-E50E24DCCA9E"
_NUS_RX_UUID = "6E400002-B5A3-F393-E0A9-E50E24DCCA9E"   # host escribe aquí
_NUS_TX_UUID = "6E400003-B5A3-F393-E0A9-E50E24DCCA9E"   # device notifica aquí


# ═══════════════════════════════════════════════════════════════════════════
# USB UART (consola USB-CDC del ESP32-S3, en paralelo con HID)
# ═══════════════════════════════════════════════════════════════════════════
def init_usb():
    """Prepara la escucha de handshake por USB UART (stdin binario)."""
    global _poll
    _poll = select.poll()
    _poll.register(sys.stdin, select.POLLIN)


def _usb_read_available():
    """Lee todos los bytes disponibles en stdin sin bloquear."""
    data = b""
    while _poll and _poll.poll(0):
        ch = sys.stdin.buffer.read(1)
        if not ch:
            break
        data += ch
    return data


def usb_check_handshake():
    """Escucha 0xAA 0x55. Si llega, responde 0x55 0xAA y activa modo USB."""
    global _stdin_buf, _mode
    _stdin_buf += _usb_read_available()
    idx = _stdin_buf.find(config.HANDSHAKE)
    if idx >= 0:
        _stdin_buf = _stdin_buf[idx + len(config.HANDSHAKE):]
        sys.stdout.buffer.write(config.HANDSHAKE_ACK)
        _mode = MODE_USB
        return True
    # Evitar crecimiento sin límite
    if len(_stdin_buf) > 64:
        _stdin_buf = _stdin_buf[-2:]
    return False


# ═══════════════════════════════════════════════════════════════════════════
# BLE — advertising "M2-DAQ" con servicio NUS
# ═══════════════════════════════════════════════════════════════════════════
def _ble_irq(event, data):
    global _ble_connected, _ble_conn, _ble_rx_buf, _mode
    if event == 1:      # _IRQ_CENTRAL_CONNECT
        _ble_conn = data[0]
        _ble_connected = True
        _mode = MODE_BLE
    elif event == 2:    # _IRQ_CENTRAL_DISCONNECT
        _ble_connected = False
        _ble_conn = None
        if _mode == MODE_BLE:
            _mode = MODE_NONE
        try:
            _advertise()
        except Exception:
            pass
    elif event == 3:    # _IRQ_GATTS_WRITE
        conn_handle, attr_handle = data
        if attr_handle == _rx_handle:
            _ble_rx_buf += _ble.gatts_read(_rx_handle)


def _advertise():
    name = config.BLE_NAME.encode()
    adv = b"\x02\x01\x06" + bytes((len(name) + 1, 0x09)) + name
    _ble.gap_advertise(100_000, adv_data=adv)


def start_ble():
    """Activa BLE advertising. Retorna True si BLE está disponible."""
    global _ble, _tx_handle, _rx_handle
    try:
        import bluetooth
        _ble = bluetooth.BLE()
        _ble.active(True)
        _ble.irq(_ble_irq)
        nus = (
            bluetooth.UUID(_NUS_UUID),
            (
                (bluetooth.UUID(_NUS_TX_UUID), bluetooth.FLAG_NOTIFY),
                (bluetooth.UUID(_NUS_RX_UUID), bluetooth.FLAG_WRITE | bluetooth.FLAG_WRITE_NO_RESPONSE),
            ),
        )
        ((_tx_handle, _rx_handle),) = _ble.gatts_register_services((nus,))
        _ble.config(gap_name=config.BLE_NAME)
        _advertise()
        print("[transport] BLE advertising como '%s'." % config.BLE_NAME)
        return True
    except Exception as e:
        print("[transport] BLE no disponible:", e)
        _ble = None
        return False


def stop_ble():
    global _ble
    if _ble is not None:
        try:
            _ble.gap_advertise(None)
            _ble.active(False)
        except Exception:
            pass
        _ble = None


def ble_connected():
    return _ble_connected


# ═══════════════════════════════════════════════════════════════════════════
# API común
# ═══════════════════════════════════════════════════════════════════════════
def mode():
    return _mode


def send(frame):
    """Envía un frame binario por el canal activo. Silencioso si no hay canal."""
    if _mode == MODE_USB:
        try:
            sys.stdout.buffer.write(frame)
        except Exception:
            pass
    elif _mode == MODE_BLE and _ble_connected:
        try:
            _ble.gatts_notify(_ble_conn, _tx_handle, frame)
        except Exception:
            pass


def _parse_cmds(buf):
    """Extrae comandos de 3 bytes (0xBB cmd arg) del buffer. Retorna resto."""
    while True:
        idx = buf.find(bytes([config.CMD_MAGIC]))
        if idx < 0:
            return b""
        buf = buf[idx:]
        if len(buf) < 3:
            return buf
        _rx_cmds.append((buf[1], buf[2]))
        buf = buf[3:]


def poll_commands():
    """Retorna lista de (cmd, arg) recibidos desde el host y vacía la cola."""
    global _stdin_buf, _ble_rx_buf, _rx_cmds
    if _mode == MODE_USB:
        _stdin_buf += _usb_read_available()
        _stdin_buf = _parse_cmds(_stdin_buf)
    elif _mode == MODE_BLE and _ble_rx_buf:
        _ble_rx_buf = _parse_cmds(_ble_rx_buf)
    cmds, _rx_cmds = _rx_cmds, []
    return cmds
