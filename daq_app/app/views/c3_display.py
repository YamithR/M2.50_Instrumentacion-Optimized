# c3_display.py — Réplica de la pantalla GC9A01 del ESP32-C3 dentro de la app.
# No se conecta al C3: toma los datos directamente de los frames del ESP32-S3
# (o del simulador). Misma lógica visual que firmware_c3/display.py:
#   · Arco perimetral 360° = cargador lleno; se vacía de ARRIBA hacia ABAJO
#     (el remanente queda anclado en la parte inferior).
#   · Verde >50 %, amarillo 20–50 %, rojo <20 %, rojo parpadeante con 0 balas.
#   · 3 cartuchos .50 estáticos. Al disparar: el saliente salta con giro
#     hacia afuera mientras el entrante aparece con fade-in en su lugar.
#   · Al completarse una recarga (S1 sostenido 2.5 s): dos flechas
#     circulares girando (misma dirección arcos+puntas) durante 1 s.
#   · Texto "actuales / máx".

import math
import time

from PySide6.QtCore import QPointF, QRectF, Qt, QTimer, Signal
from PySide6.QtGui import (
    QBrush, QColor, QFont, QPainter, QPainterPath, QPen, QPolygonF,
)
from PySide6.QtWidgets import QVBoxLayout, QWidget

from ..connection.protocol import Frame

_GREEN = QColor("#2ecc40")
_YELLOW = QColor("#ffdc00")
_RED = QColor("#ff4136")
_GREY = QColor("#5a5a5a")
_COPPER = QColor("#c46a32")
_BRASS = QColor("#d6a83c")
_BLACK = QColor("#000000")
_WHITE = QColor("#ffffff")

_ROW_Y = 102.0          # centro vertical de la fila de cartuchos
_SLOT_DX = 52.0         # separación horizontal entre cartuchos
_RELOAD_SHOW_S = 1.0    # duración del spinner tras una recarga efectiva
_ANIM_STEP = 0.14       # avance de la transición de disparo por tick (60 ms)


class C3DisplayWidget(QWidget):
    """Widget circular 240×240 (escalable) que replica la GC9A01."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setMinimumSize(260, 260)
        self._current = 0
        self._maximum = 50
        self._have_data = False
        self._blink = False
        self._flash = 0
        self._spin_angle = 0.0
        self._reload_until = 0.0     # monotonic() hasta el cual se ve el spinner
        self._anim_t = None          # None = sin transición; 0..1 = progreso

        self._anim = QTimer(self)
        self._anim.setInterval(60)
        self._anim.timeout.connect(self._on_anim)
        self._anim.start()

    def update_frame(self, f: Frame):
        cur = f.rounds_left
        if self._have_data and cur < self._current:
            self._flash = 3
            self._anim_t = 0.0                   # dispara la transición
        if self._have_data and cur > self._current:
            self._reload_until = time.monotonic() + _RELOAD_SHOW_S
        self._current = cur
        self._maximum = max(1, f.magazine_max)
        self._have_data = True
        self.update()

    def _reloading(self) -> bool:
        return time.monotonic() < self._reload_until

    def _on_anim(self):
        self._blink = not self._blink
        if self._flash > 0:
            self._flash -= 1
        if self._reloading():
            self._spin_angle = (self._spin_angle + 14) % 360
        if self._anim_t is not None:
            self._anim_t += _ANIM_STEP
            if self._anim_t >= 1.0:
                self._anim_t = None
        self.update()

    def paintEvent(self, _event):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)

        side = min(self.width(), self.height())
        p.translate((self.width() - side) / 2, (self.height() - side) / 2)
        scale = side / 240.0
        p.scale(scale, scale)

        # Fondo circular negro (flash naranja oscuro en disparo)
        bg = QColor(60, 25, 0) if self._flash > 0 else _BLACK
        p.setPen(Qt.NoPen)
        p.setBrush(QBrush(bg))
        p.drawEllipse(QRectF(0, 0, 240, 240))

        frac = self._current / self._maximum

        # Color del arco según nivel
        if not self._have_data:
            arc_color, arc_frac = _GREY, 1.0
        elif self._current <= 0:
            arc_color = _RED if self._blink else _BLACK
            arc_frac = 1.0
        else:
            arc_frac = frac
            if frac > 0.5:
                arc_color = _GREEN
            elif frac >= 0.2:
                arc_color = _YELLOW
            else:
                arc_color = _RED

        # Arco perimetral: remanente anclado ABAJO, se vacía desde ARRIBA
        pen = QPen(arc_color, 14, Qt.SolidLine, Qt.FlatCap)
        p.setPen(pen)
        p.setBrush(Qt.NoBrush)
        rect = QRectF(11, 11, 218, 218)
        span = 360.0 * arc_frac
        start = -90.0 + span / 2.0           # centro del relleno = -90° (abajo)
        p.drawArc(rect, int(start * 16), int(-span * 16))

        if self._reloading():
            self._draw_spinner(p, 120, _ROW_Y)
        else:
            self._draw_cartridges(p)

        # Contador "actuales / máx"
        p.setPen(QPen(_WHITE if self._current > 0 else _RED))
        f = QFont("Monospace", 24, QFont.Bold)
        p.setFont(f)
        txt = ("%d / %d" % (self._current, self._maximum)
               if self._have_data else "— / —")
        p.drawText(QRectF(0, 150, 240, 40), Qt.AlignCenter, txt)

        if not self._have_data:
            p.setPen(QPen(_GREY))
            p.setFont(QFont("Monospace", 9))
            p.drawText(QRectF(0, 192, 240, 20), Qt.AlignCenter,
                       "esperando datos")
        p.end()

    # ── Fila de 3 cartuchos .50 estáticos + transición de disparo ───────
    def _draw_cartridges(self, p: QPainter):
        alive = self._have_data and self._current > 0
        tip = _COPPER if alive else _GREY
        case = _BRASS if alive else _GREY
        xs = [120.0 + (k - 1) * _SLOT_DX for k in range(3)]

        # Slots 1 y 2 siempre estáticos
        for x in xs[1:]:
            self._cartridge(p, x, _ROW_Y, tip, case, scale=0.9)

        if self._anim_t is None:
            self._cartridge(p, xs[0], _ROW_Y, tip, case, scale=0.9)
            return

        t = min(1.0, self._anim_t)
        # Saliente: salto hacia arriba-izquierda con giro y desvanecimiento
        p.save()
        p.setOpacity(1.0 - t)
        jx = xs[0] - 55.0 * t
        jy = _ROW_Y - 90.0 * t * (2.0 - t)
        self._cartridge(p, jx, jy, tip, case, scale=0.9, angle=-340.0 * t)
        p.restore()
        # Entrante: fade-in en el mismo slot
        p.save()
        p.setOpacity(t)
        self._cartridge(p, xs[0], _ROW_Y, tip, case, scale=0.9)
        p.restore()

    def _cartridge(self, p: QPainter, x, y, tip, case, scale=1.0, angle=0.0):
        """Cartucho .50 BMG vertical (punta arriba): culote, cuerpo,
        hombro, cuello y bala ojival de cobre."""
        p.save()
        p.translate(x, y)
        if angle:
            p.rotate(angle)
        p.scale(scale, scale)
        p.setPen(Qt.NoPen)

        p.setBrush(QBrush(case))
        p.drawRect(QRectF(-13, 28, 26, 5))                       # culote (rim)
        p.drawRect(QRectF(-11, 0, 22, 28))                       # cuerpo
        p.drawPolygon(QPolygonF([                                # hombro
            QPointF(-11, 0), QPointF(-6.5, -8),
            QPointF(6.5, -8), QPointF(11, 0)]))
        p.drawRect(QRectF(-6.5, -14, 13, 6))                     # cuello

        path = QPainterPath()                                    # bala (ojiva)
        path.moveTo(-6.5, -14)
        path.lineTo(-6.5, -20)
        path.quadTo(-6.0, -33, 0, -41)
        path.quadTo(6.0, -33, 6.5, -20)
        path.lineTo(6.5, -14)
        path.closeSubpath()
        p.setBrush(QBrush(tip))
        p.drawPath(path)

        hl = QColor(255, 255, 255, 90)                           # brillo sutil
        p.setPen(QPen(hl, 2))
        p.drawLine(QPointF(-7, 3), QPointF(-7, 25))
        p.drawLine(QPointF(-3.5, -18), QPointF(-1.5, -32))
        p.restore()

    # ── Spinner de recarga (dos flechas circulares, mismo sentido) ──────
    def _draw_spinner(self, p: QPainter, cx, cy):
        r = 34.0
        p.save()
        p.translate(cx, cy)
        p.rotate(self._spin_angle)          # todo el conjunto gira junto
        pen = QPen(_WHITE, 5, Qt.SolidLine, Qt.RoundCap)
        p.setPen(pen)
        p.setBrush(Qt.NoBrush)
        rect = QRectF(-r, -r, 2 * r, 2 * r)
        for k in range(2):
            base = k * 180.0
            p.drawArc(rect, int(base * 16), int(130 * 16))
            self._arrow_head(p, r, base)
        p.restore()

    @staticmethod
    def _arrow_head(p: QPainter, r, angle_deg):
        """Punta en el extremo delantero del arco (sentido horario, igual
        que la rotación del conjunto)."""
        a = math.radians(angle_deg)
        tipx, tipy = r * math.cos(a), -r * math.sin(a)
        tx, ty = math.sin(a), math.cos(a)      # tangente en sentido horario
        for ang in (-0.5, 0.5):
            ca, sa = math.cos(ang), math.sin(ang)
            bx = tipx - 13 * (tx * ca - ty * sa)
            by = tipy - 13 * (tx * sa + ty * ca)
            p.drawLine(QPointF(tipx, tipy), QPointF(bx, by))


class C3DisplayWindow(QWidget):
    """Ventana flotante 'Pantalla C3' alimentada por frames del ESP32-S3."""
    closed = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Pantalla C3 — Contador de balas")
        self.setWindowFlag(self.windowFlags().Window, True)
        self.setStyleSheet("background:#1a1a1a;")
        lay = QVBoxLayout(self)
        self.display = C3DisplayWidget()
        lay.addWidget(self.display)
        self.resize(320, 340)

    def update_frame(self, f: Frame):
        self.display.update_frame(f)

    def closeEvent(self, event):
        self.closed.emit()
        super().closeEvent(event)
