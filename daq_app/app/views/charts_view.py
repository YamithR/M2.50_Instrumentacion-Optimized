# charts_view.py — Gráficas en tiempo real (pyqtgraph):
#   · ENC_H y ENC_V (cuentas vs tiempo)
#   · Timeline binario S1/S2/S3
#   · Métricas: ángulos, frecuencia de frames y latencia

import time
from collections import deque

import pyqtgraph as pg
from PySide6.QtWidgets import QGroupBox, QLabel, QVBoxLayout

from ..connection.protocol import Frame

_WINDOW_S = 10.0        # ventana visible en segundos
_MAXLEN = 1000          # 50 Hz × 20 s de margen


class ChartsView(QGroupBox):
    def __init__(self, parent=None):
        super().__init__("GRÁFICAS TIEMPO REAL", parent)
        pg.setConfigOptions(antialias=False)
        lay = QVBoxLayout(self)

        self._t = deque(maxlen=_MAXLEN)
        self._eh = deque(maxlen=_MAXLEN)
        self._ev = deque(maxlen=_MAXLEN)
        self._s1 = deque(maxlen=_MAXLEN)
        self._s2 = deque(maxlen=_MAXLEN)
        self._s3 = deque(maxlen=_MAXLEN)

        # ── Encoders ────────────────────────────────────────────────────
        self._plot_enc = pg.PlotWidget(title="Encoders (cuentas)")
        self._plot_enc.addLegend(offset=(10, 10))
        self._plot_enc.showGrid(x=True, y=True, alpha=0.3)
        self._curve_h = self._plot_enc.plot(pen=pg.mkPen("#00bfff", width=2), name="ENC_H")
        self._curve_v = self._plot_enc.plot(pen=pg.mkPen("#ff851b", width=2), name="ENC_V")
        lay.addWidget(self._plot_enc, stretch=3)

        # ── Timeline binario S1/S2/S3 ───────────────────────────────────
        self._plot_bin = pg.PlotWidget(title="S1 / S2 / S3 (timeline binario)")
        self._plot_bin.setYRange(-0.5, 5.5)
        self._plot_bin.getAxis("left").setTicks(
            [[(0.5, "S3"), (2.5, "S2"), (4.5, "S1")]])
        self._curve_s1 = self._plot_bin.plot(pen=pg.mkPen("#2ecc40", width=2))
        self._curve_s2 = self._plot_bin.plot(pen=pg.mkPen("#ffdc00", width=2))
        self._curve_s3 = self._plot_bin.plot(pen=pg.mkPen("#ff4136", width=2))
        lay.addWidget(self._plot_bin, stretch=2)

        # ── Métricas ────────────────────────────────────────────────────
        self._lbl = QLabel("ENC_H: —   ENC_V: —   Hz: —   Latencia: —")
        lay.addWidget(self._lbl)

        self._last_wall = None
        self._hz_acc = deque(maxlen=50)

    def clear(self):
        for d in (self._t, self._eh, self._ev, self._s1, self._s2, self._s3):
            d.clear()
        self._last_wall = None
        self._hz_acc.clear()

    def update_frame(self, f: Frame):
        now = time.monotonic()
        t = f.ts_ms / 1000.0
        self._t.append(t)
        self._eh.append(f.enc_h)
        self._ev.append(f.enc_v)
        self._s1.append(4 + (1 if f.s1 else 0))
        self._s2.append(2 + (1 if f.s2 else 0))
        self._s3.append(0 + (1 if f.s3 else 0))

        # Frecuencia y latencia estimadas (reloj local vs timestamp device)
        if self._last_wall is not None:
            dt = now - self._last_wall
            if dt > 0:
                self._hz_acc.append(1.0 / dt)
        self._last_wall = now

        ts = list(self._t)
        self._curve_h.setData(ts, list(self._eh))
        self._curve_v.setData(ts, list(self._ev))
        self._curve_s1.setData(ts, list(self._s1))
        self._curve_s2.setData(ts, list(self._s2))
        self._curve_s3.setData(ts, list(self._s3))
        if ts:
            x_max = ts[-1]
            self._plot_enc.setXRange(max(0, x_max - _WINDOW_S), x_max)
            self._plot_bin.setXRange(max(0, x_max - _WINDOW_S), x_max)

        hz = sum(self._hz_acc) / len(self._hz_acc) if self._hz_acc else 0.0
        lat_ms = (1000.0 / hz / 2) if hz > 1 else 0.0
        enc_h_deg = f.enc_h * 180 / 1000
        enc_v_deg = f.enc_v * 45 / 500
        self._lbl.setText(
            f"ENC_H: {enc_h_deg:+.0f}°   ENC_V: {enc_v_deg:+.0f}°   "
            f"Hz: {hz:.0f}   Latencia: {lat_ms:.0f}ms")
