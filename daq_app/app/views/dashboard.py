# dashboard.py — Vista principal de datos en vivo:
# columna izquierda (sensores + válvula + balas) y derecha (gráficas).

from PySide6.QtCore import Signal
from PySide6.QtWidgets import QHBoxLayout, QVBoxLayout, QWidget

from ..connection.protocol import Frame
from .ammo_panel import AmmoPanel
from .charts_view import ChartsView
from .sensors_panel import SensorsPanel


class Dashboard(QWidget):
    pulse_requested = Signal(int)     # duración en ms del pulso manual

    def __init__(self, parent=None):
        super().__init__(parent)
        root = QHBoxLayout(self)

        left = QVBoxLayout()
        self.sensors = SensorsPanel()
        self.ammo = AmmoPanel()
        self.ammo.pulse_requested.connect(self.pulse_requested)
        left.addWidget(self.sensors)
        left.addWidget(self.ammo)
        left.addStretch()

        self.charts = ChartsView()

        root.addLayout(left, stretch=1)
        root.addWidget(self.charts, stretch=3)

    def update_frame(self, f: Frame):
        self.sensors.update_frame(f)
        self.ammo.update_frame(f)
        self.charts.update_frame(f)

    def clear(self):
        self.charts.clear()
