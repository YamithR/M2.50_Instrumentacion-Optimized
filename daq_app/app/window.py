# window.py — Ventana principal M2.50 DAQ.
# Barra superior: estado, selector de puerto, [Conectar] [Pantalla C3] [Simular].
# Conexión solo por USB (handshake binario). Si falla, ofrece el simulador.

from PySide6.QtWidgets import (
    QComboBox, QHBoxLayout, QLabel, QMainWindow, QMessageBox, QPushButton,
    QVBoxLayout, QWidget,
)

from .connection.protocol import Frame, build_sensor_override, build_valve_pulse
from .connection.usb_handler import UsbHandler, scan_ports
from .simulator.sim_engine import SimEngine
from .views.c3_display import C3DisplayWindow
from .views.dashboard import Dashboard
from .views.sim_window import SimWindow


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("M2.50 DAQ")
        self.resize(1100, 650)

        self._usb: UsbHandler | None = None
        self._connected = False
        self._use_sim = False
        self._link_was_on = False

        self._sim_engine = SimEngine(self)
        self._sim_engine.frame_ready.connect(self._on_sim_frame)
        self._sim_window: SimWindow | None = None
        self._c3_window: C3DisplayWindow | None = None

        # ── Barra superior ──────────────────────────────────────────────
        top = QHBoxLayout()
        title = QLabel("M2.50 DAQ")
        title.setStyleSheet("font-weight:bold;font-size:16px;")
        self._status = QLabel("🔴 Desconectado")
        self._ports = QComboBox()
        self._refresh_ports()
        self._btn_connect = QPushButton("Conectar")
        self._btn_connect.clicked.connect(self._on_connect_clicked)
        btn_c3 = QPushButton("Pantalla C3")
        btn_c3.clicked.connect(self._open_c3_display)
        btn_sim = QPushButton("Simular")
        btn_sim.clicked.connect(self._open_simulator)
        top.addWidget(title)
        top.addSpacing(20)
        top.addWidget(self._status)
        top.addStretch()
        top.addWidget(self._ports)
        top.addWidget(self._btn_connect)
        top.addWidget(btn_c3)
        top.addWidget(btn_sim)

        # ── Dashboard ───────────────────────────────────────────────────
        self.dashboard = Dashboard()
        self.dashboard.pulse_requested.connect(self._send_command)

        central = QWidget()
        lay = QVBoxLayout(central)
        lay.addLayout(top)
        lay.addWidget(self.dashboard)
        self.setCentralWidget(central)

    # ═══════════════════════════ Conexión USB ════════════════════════════
    def _refresh_ports(self):
        self._ports.clear()
        self._ports.addItem("Auto")
        for p in scan_ports():
            self._ports.addItem(p)

    def _on_connect_clicked(self):
        if self._connected:
            self._disconnect()
            return
        self._btn_connect.setEnabled(False)
        self._status.setText("⏳ Buscando USB…")
        port = None if self._ports.currentText() == "Auto" else self._ports.currentText()
        self._usb = UsbHandler(port)
        self._usb.frame_received.connect(self._on_real_frame)
        self._usb.connected.connect(self._on_usb_connected)
        self._usb.disconnected.connect(self._on_usb_failed)
        self._usb.start()

    def _on_usb_connected(self, port: str):
        self._connected = True
        self._status.setText(f"🔵 USB — {port}")
        self._btn_connect.setText("Desconectar")
        self._btn_connect.setEnabled(True)
        self.dashboard.clear()

    def _on_usb_failed(self, reason: str):
        if self._connected:                     # desconexión en caliente
            self._disconnect()
            return
        self._usb = None
        self._status.setText("🔴 Desconectado")
        self._btn_connect.setText("Conectar")
        self._btn_connect.setEnabled(True)
        ans = QMessageBox.question(
            self, "Sin conexión",
            f"No se encontró el ESP32-S3 por USB.\n({reason})\n\n"
            "¿Activar el modo Simulador?")
        if ans == QMessageBox.StandardButton.Yes:
            self._open_simulator(activate=True)

    def _disconnect(self):
        if self._usb is not None:
            self._usb.stop()
            self._usb = None
        self._connected = False
        self._status.setText("🔴 Desconectado")
        self._btn_connect.setText("Conectar")
        self._btn_connect.setEnabled(True)
        self._refresh_ports()

    # ═══════════════════════════ Datos ═══════════════════════════════════
    def _dispatch(self, f: Frame):
        self.dashboard.update_frame(f)
        if self._c3_window is not None:
            self._c3_window.update_frame(f)

    def _on_real_frame(self, f: Frame):
        if not self._use_sim:
            self._dispatch(f)

    def _on_sim_frame(self, f: Frame):
        if self._use_sim:
            self._dispatch(f)

    def _send_command(self, duration_ms: int):
        """Pulso manual: en simulador dispara el mismo flujo que un disparo
        real (cuenta bala, válvula, gráfica); en USB envía el comando 0xBB."""
        if self._use_sim:
            self._sim_engine.manual_pulse(duration_ms)
        elif self._connected and self._usb is not None:
            self._usb.send_command(build_valve_pulse(duration_ms))

    def _on_control_link(self, s1: bool, s2: bool, s3: bool, enable: bool):
        """ControlLink: fuerza los sensores físicos del ESP32-S3 desde la UI
        (comando 0xBB 0x02). Solo envía si está o estuvo habilitado."""
        if not (enable or self._link_was_on):
            return
        self._link_was_on = enable
        if self._connected and self._usb is not None:
            self._usb.send_command(build_sensor_override(s1, s2, s3, enable))

    def _on_mouse_event(self, evt):
        """ControlLink + movimiento de encoder: mueve el mouse del PC."""
        if not self._link_was_on:
            return
        try:
            from pynput.mouse import Controller
            m = Controller()
            m.move(evt.dx, -evt.dy)
        except ImportError:
            pass

    def _on_fire_event(self):
        """ControlLink + flanco S3: clic HID en el PC."""
        if not self._link_was_on:
            return
        try:
            from pynput.mouse import Controller, Button
            m = Controller()
            m.click(Button.left, 1)
        except ImportError:
            pass

    # ═══════════════════════════ Pantalla C3 ═════════════════════════════
    def _open_c3_display(self):
        if self._c3_window is None:
            self._c3_window = C3DisplayWindow()
            self._c3_window.closed.connect(self._on_c3_closed)
        self._c3_window.show()
        self._c3_window.raise_()

    def _on_c3_closed(self):
        self._c3_window = None

    # ═══════════════════════════ Simulador ═══════════════════════════════
    def _open_simulator(self, activate: bool = False):
        if self._sim_window is None:
            self._sim_window = SimWindow(self._sim_engine)
            self._sim_window.swap_requested.connect(self._on_swap)
            self._sim_window.control_link_changed.connect(self._on_control_link)
            self._sim_engine.mouse_moved.connect(self._on_mouse_event)
            self._sim_engine.fire_click.connect(self._on_fire_event)
            self._sim_window.closed.connect(self._on_sim_closed)
        self._sim_window.show()
        self._sim_window.raise_()
        if activate:
            self._sim_window.set_sim_active(True)

    def _on_swap(self, use_sim: bool):
        self._use_sim = use_sim
        self.dashboard.clear()
        if use_sim:
            self._status.setText("🟣 Simulador")
        elif self._connected:
            self._status.setText("🔵 USB")
        else:
            self._status.setText("🔴 Desconectado")

    def _on_sim_closed(self):
        if self._use_sim:
            self._sim_window.set_sim_active(False)

    # ═══════════════════════════ Cierre ═══════════════════════════════════
    def closeEvent(self, event):
        self._sim_engine.stop()
        self._disconnect()
        if self._sim_window is not None:
            self._sim_window.close()
        if self._c3_window is not None:
            self._c3_window.close()
        super().closeEvent(event)
