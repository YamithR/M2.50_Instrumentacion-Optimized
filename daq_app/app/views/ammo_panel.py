# ammo_panel.py — Contador de balas visual + botón pulso manual de válvula.
# El pulso envía el comando 0xBB 0x01 <duración/10ms> al ESP32-S3.

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QGroupBox, QHBoxLayout, QLabel, QProgressBar, QPushButton, QSlider,
    QVBoxLayout,
)

from ..connection.protocol import Frame


class AmmoPanel(QGroupBox):
    pulse_requested = Signal(int)     # duración en ms; la ventana decide destino (USB/simulador)

    def __init__(self, parent=None):
        super().__init__("BALAS", parent)
        lay = QVBoxLayout(self)

        self._bar = QProgressBar(minimum=0, maximum=50, value=0)
        self._bar.setFormat("%v/%m")
        lay.addWidget(self._bar)

        lay.addSpacing(8)
        self._btn = QPushButton("⚡ PULSO MANUAL")
        self._btn.clicked.connect(self._on_pulse)
        lay.addWidget(self._btn)

        row = QHBoxLayout()
        row.addWidget(QLabel("Duración:"))
        self._sld = QSlider(Qt.Horizontal, minimum=10, maximum=500,
                            singleStep=10, value=50)
        self._sld.valueChanged.connect(self._on_duration)
        self._lbl_ms = QLabel("50 ms")
        row.addWidget(self._sld)
        row.addWidget(self._lbl_ms)
        lay.addLayout(row)

    def _on_duration(self, v):
        self._lbl_ms.setText(f"{v} ms")

    def _on_pulse(self):
        self.pulse_requested.emit(self._sld.value())

    def update_frame(self, f: Frame):
        self._bar.setMaximum(max(1, f.magazine_max))
        self._bar.setValue(f.rounds_left)
        frac = f.rounds_left / max(1, f.magazine_max)
        if frac > 0.5:
            color = "#2ecc40"
        elif frac >= 0.2:
            color = "#ffdc00"
        else:
            color = "#ff4136"
        self._bar.setStyleSheet(
            f"QProgressBar::chunk {{ background: {color}; }}")
        self._btn.setEnabled(not f.valve_blocked)
