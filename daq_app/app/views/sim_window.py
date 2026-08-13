# sim_window.py — Ventana flotante del simulador intercambiable.
# "Intercambiar con Real ⇄" conecta los frames del simulador a las mismas
# vistas del dashboard, permitiendo validar la UI sin hardware.

from PySide6.QtCore import Signal
from PySide6.QtWidgets import QLabel, QPushButton, QVBoxLayout, QWidget

from ..simulator.sim_controls import SimControls
from ..simulator.sim_engine import SimEngine


class SimWindow(QWidget):
    swap_requested = Signal(bool)   # True = usar simulador, False = usar real
    control_link_changed = Signal(bool, bool, bool, bool)   # s1, s2, s3, on
    closed = Signal()

    def __init__(self, engine: SimEngine, parent=None):
        super().__init__(parent)
        self.setWindowTitle("SIMULADOR — M2.50 DAQ")
        self.setWindowFlag(self.windowFlags().Window, True)
        self._engine = engine

        lay = QVBoxLayout(self)
        self._btn_swap = QPushButton("Intercambiar con Real ⇄")
        self._btn_swap.setCheckable(True)
        self._btn_swap.toggled.connect(self._on_swap)
        lay.addWidget(self._btn_swap)

        self._lbl = QLabel("Fuente actual del dashboard: REAL")
        lay.addWidget(self._lbl)

        controls = SimControls(engine)
        controls.control_link_changed.connect(self.control_link_changed)
        lay.addWidget(controls)

    def set_sim_active(self, active: bool):
        self._btn_swap.setChecked(active)

    def _on_swap(self, use_sim: bool):
        if use_sim:
            self._engine.start()
            self._lbl.setText("Fuente actual del dashboard: SIMULADOR")
        else:
            self._engine.stop()
            self._lbl.setText("Fuente actual del dashboard: REAL")
        self.swap_requested.emit(use_sim)

    def closeEvent(self, event):
        self.closed.emit()
        super().closeEvent(event)
