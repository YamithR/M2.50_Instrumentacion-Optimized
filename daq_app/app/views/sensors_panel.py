# sensors_panel.py — LEDs virtuales S1/S2/S3 + estado de la electroválvula.

from PySide6.QtWidgets import QGroupBox, QHBoxLayout, QLabel, QVBoxLayout, QWidget

from ..connection.protocol import Frame

_LED_BASE = "border-radius:9px;min-width:18px;max-width:18px;min-height:18px;max-height:18px;"
_LED_OFF = f"background:#3a3a3a;{_LED_BASE}"


class _LedRow(QWidget):
    def __init__(self, name, desc, color="#2ecc40", parent=None):
        super().__init__(parent)
        self._on_style = f"background:{color};{_LED_BASE}"
        lay = QHBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        self._led = QLabel()
        self._led.setStyleSheet(_LED_OFF)
        lay.addWidget(self._led)
        lay.addWidget(QLabel(f"{name}  [{desc}]"))
        lay.addStretch()

    def set_on(self, on: bool):
        self._led.setStyleSheet(self._on_style if on else _LED_OFF)


class SensorsPanel(QGroupBox):
    def __init__(self, parent=None):
        super().__init__("SENSORES", parent)
        lay = QVBoxLayout(self)
        self._s1 = _LedRow("S1", "BLOQUEADO")
        self._s2 = _LedRow("S2", "RETENEDOR")
        self._s3 = _LedRow("S3", "VÁLVULA")
        for w in (self._s1, self._s2, self._s3):
            lay.addWidget(w)

        lay.addSpacing(8)
        lay.addWidget(QLabel("ELECTROVÁLVULA"))
        self._valve_led = _LedRow("EV", "ACTIVADA", color="#00bfff")
        lay.addWidget(self._valve_led)
        self._valve = QLabel("Estado: —")
        lay.addWidget(self._valve)

    def update_frame(self, f: Frame):
        self._s1.set_on(f.s1)
        self._s2.set_on(f.s2)
        self._s3.set_on(f.s3)
        self._valve_led.set_on(f.valve)
        if f.valve_blocked:
            self._valve.setText("Estado: ■ BLOQUEADA (sin munición)")
            self._valve.setStyleSheet("color:#ff4136;font-weight:bold;")
        elif f.valve:
            self._valve.setText("Estado: ● ABIERTA")
            self._valve.setStyleSheet("color:#00bfff;font-weight:bold;")
        else:
            self._valve.setText("Estado: ○ CERRADA")
            self._valve.setStyleSheet("")
