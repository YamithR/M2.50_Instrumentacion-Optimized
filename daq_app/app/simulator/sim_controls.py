# sim_controls.py — Sliders y controles interactivos del simulador.

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QCheckBox, QGridLayout, QHBoxLayout, QLabel, QPushButton, QSlider,
    QSpinBox, QVBoxLayout, QWidget,
)

from .sim_engine import SimEngine


class SimControls(QWidget):
    # ControlLink: (s1, s2, s3, habilitado) → forzar sensores físicos por USB
    control_link_changed = Signal(bool, bool, bool, bool)

    def __init__(self, engine: SimEngine, parent=None):
        super().__init__(parent)
        self._engine = engine
        root = QVBoxLayout(self)

        # ── Toggles S1 / S2 / S3 ────────────────────────────────────────
        row = QHBoxLayout()
        self._btn_s1 = self._toggle("S1", self._on_s1)
        self._btn_s2 = self._toggle("S2", self._on_s2)
        self._btn_s3 = self._toggle("S3", self._on_s3)
        for b in (self._btn_s1, self._btn_s2, self._btn_s3):
            row.addWidget(b)
        root.addLayout(row)

        # ── ControlLink: los toggles anteriores actúan sobre el hardware ─
        self._chk_link = QCheckBox(
            "ControlLink — forzar sensores físicos (S1/S2/S3) por USB")
        self._chk_link.toggled.connect(self._emit_link)
        root.addWidget(self._chk_link)

        # ── Sliders de encoders ─────────────────────────────────────────
        grid = QGridLayout()
        self._lbl_h = QLabel("+0")
        self._lbl_v = QLabel("+0")
        self._sld_h = self._slider(-1000, 1000, self._on_enc_h)
        self._sld_v = self._slider(-500, 500, self._on_enc_v)
        grid.addWidget(QLabel("ENC_H:"), 0, 0)
        grid.addWidget(self._sld_h, 0, 1)
        grid.addWidget(self._lbl_h, 0, 2)
        grid.addWidget(QLabel("ENC_V:"), 1, 0)
        grid.addWidget(self._sld_v, 1, 1)
        grid.addWidget(self._lbl_v, 1, 2)
        root.addLayout(grid)

        # ── Balas y cadencia ────────────────────────────────────────────
        ammo = QGridLayout()
        self._spin_max = QSpinBox(minimum=1, maximum=255, value=engine.magazine_max)
        self._spin_cur = QSpinBox(minimum=0, maximum=255, value=engine.rounds_left)
        self._spin_max.valueChanged.connect(self._on_max)
        self._spin_cur.valueChanged.connect(engine.set_current_rounds)
        ammo.addWidget(QLabel("Balas Max:"), 0, 0)
        ammo.addWidget(self._spin_max, 0, 1)
        ammo.addWidget(QLabel("Actuales:"), 0, 2)
        ammo.addWidget(self._spin_cur, 0, 3)

        self._lbl_rpm = QLabel(f"{engine.rate_rpm} rpm")
        self._sld_rpm = self._slider(60, 900, self._on_rpm)
        self._sld_rpm.setValue(engine.rate_rpm)
        ammo.addWidget(QLabel("Cadencia disparo:"), 1, 0)
        ammo.addWidget(self._sld_rpm, 1, 1, 1, 2)
        ammo.addWidget(self._lbl_rpm, 1, 3)
        root.addLayout(ammo)

        # ── Acciones ────────────────────────────────────────────────────
        actions = QHBoxLayout()
        self._btn_burst = QPushButton("▶ Simular ráfaga")
        self._btn_burst.setCheckable(True)
        self._btn_burst.toggled.connect(self._on_burst)
        btn_reload = QPushButton("⟳ Recargar")
        btn_reload.clicked.connect(self._on_reload)
        actions.addWidget(self._btn_burst)
        actions.addWidget(btn_reload)
        root.addLayout(actions)

    # ── Helpers ─────────────────────────────────────────────────────────
    def _toggle(self, name, setter):
        btn = QPushButton(f"{name} [toggle]")
        btn.setCheckable(True)
        btn.toggled.connect(setter)
        return btn

    def _slider(self, mn, mx, cb):
        sld = QSlider(Qt.Horizontal, minimum=mn, maximum=mx)
        sld.valueChanged.connect(cb)
        return sld

    # ── Callbacks ───────────────────────────────────────────────────────
    def _on_s1(self, v):
        self._engine.s1 = v
        self._emit_link()

    def _on_s2(self, v):
        self._engine.s2 = v
        self._emit_link()

    def _on_s3(self, v):
        self._engine.s3 = v
        self._emit_link()

    def _emit_link(self, _checked=None):
        self.control_link_changed.emit(
            self._btn_s1.isChecked(), self._btn_s2.isChecked(),
            self._btn_s3.isChecked(), self._chk_link.isChecked())

    def _on_enc_h(self, v):
        self._engine.enc_h = v
        self._lbl_h.setText(f"{v:+d}")

    def _on_enc_v(self, v):
        self._engine.enc_v = v
        self._lbl_v.setText(f"{v:+d}")

    def _on_max(self, v):
        self._engine.magazine_max = v
        self._spin_cur.setMaximum(v)

    def _on_rpm(self, v):
        self._engine.rate_rpm = v
        self._lbl_rpm.setText(f"{v} rpm")

    def _on_burst(self, active):
        if active:
            self._engine.start_burst()
            self._btn_burst.setText("■ Detener ráfaga")
        else:
            self._engine.stop_burst()
            self._btn_burst.setText("▶ Simular ráfaga")

    def _on_reload(self):
        self._engine.reload()
        self._spin_cur.setValue(self._engine.rounds_left)
