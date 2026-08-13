# display.py — Motor gráfico: animación balística + arco circular.
# Pantalla GC9A01 240×240:
#   · Borde arco 360° = cargador lleno; se reduce de ARRIBA hacia ABAJO
#     (el remanente queda anclado en la parte inferior).
#   · Colores: verde (>50%), amarillo (20–50%), rojo (<20%),
#     rojo parpadeante (0 balas).
#   · 3 cartuchos calibre .50 estáticos (dibujados, no texto). Al disparar:
#     el saliente salta hacia afuera con giro mientras el entrante aparece
#     con fade-in (aumento de brillo) en su lugar.
#   · Al completarse una recarga (S1 sostenido 2.5 s en el S3): dos flechas
#     circulares girando en el mismo sentido, durante 1 s (flag del S3).
#   · Texto "actuales / máx" bajo el gráfico.

import math
import time
import gc9a01
from gc9a01 import color565

_CX = 120
_CY = 120
_R_OUT = 118        # radio exterior del arco
_R_IN  = 104        # radio interior del arco
_ROW_Y = 104        # centro vertical de la fila de cartuchos / spinner
_SLOT_DX = 52       # separación horizontal entre cartuchos
_ANIM_FRAMES = 8    # duración de la transición de disparo (frames ~20 FPS)

BLACK  = color565(0, 0, 0)
WHITE  = color565(255, 255, 255)
GREY   = color565(90, 90, 90)
GREEN  = color565(0, 220, 60)
YELLOW = color565(255, 200, 0)
RED    = color565(255, 30, 30)


def _dim(r, g, b, f):
    return color565(int(r * f), int(g * f), int(b * f))


# Niveles de brillo para el fade-in del cartucho entrante (framebuf no
# soporta alpha): índice 0 = tenue … 3 = color pleno.
_BRASS_LV  = [_dim(214, 168, 60, f) for f in (0.25, 0.5, 0.75, 1.0)]
_COPPER_LV = [_dim(196, 106, 50, f) for f in (0.25, 0.5, 0.75, 1.0)]
BRASS  = _BRASS_LV[3]
COPPER = _COPPER_LV[3]


class Display:
    def __init__(self):
        import config
        self.tft = gc9a01.GC9A01(
            config.SPI_ID, config.PIN_SCK, config.PIN_MOSI,
            config.PIN_DC, config.PIN_CS, config.PIN_RST,
            bl=config.PIN_BL, baud=config.SPI_BAUD,
        )
        self.tft.backlight(True)
        self._flash_frames = 0
        self._anim_left = 0          # frames restantes de la transición
        self._blink = False
        self._spin_angle = 0

    # ── Eventos ─────────────────────────────────────────────────────────
    def fire_animation(self):
        """Flash de color + transición de cartuchos (salto/giro + fade-in)."""
        self._flash_frames = 3
        self._anim_left = _ANIM_FRAMES

    # ── Helpers de dibujo ───────────────────────────────────────────────
    def _arc(self, frac, color):
        """Arco de munición: 360° = lleno. El vacío crece desde ARRIBA
        (0°) hacia abajo; el remanente queda centrado en la parte
        inferior (180°) del círculo."""
        if frac <= 0:
            return
        tft = self.tft
        half_span = 180.0 * min(1.0, frac)        # grados a cada lado del fondo
        thick = (_R_OUT - _R_IN) // 2
        r_mid = (_R_OUT + _R_IN) // 2
        step = 2
        a = -half_span
        while a <= half_span:
            rad = math.radians(a + 90.0)          # +90° = abajo (centro del relleno)
            x = int(_CX + r_mid * math.cos(rad))
            y = int(_CY + r_mid * math.sin(rad))
            tft.ellipse(x, y, thick, thick, color, True)
            a += step

    def _cartridge(self, x, y, tip, case, horizontal=False):
        """Cartucho .50 BMG (~64 px de alto): culote, cuerpo, hombro en
        escalera, cuello y bala ojival de cobre. horizontal=True lo dibuja
        acostado (aprox. de giro durante el salto)."""
        tft = self.tft
        if not horizontal:
            tft.fill_rect(x - 12, y + 26, 24, 5, case)        # culote (rim)
            tft.fill_rect(x - 10, y - 2, 20, 28, case)        # cuerpo
            tft.fill_rect(x - 9,  y - 5, 18, 3, case)         # hombro (escalera)
            tft.fill_rect(x - 8,  y - 8, 16, 3, case)
            tft.fill_rect(x - 6,  y - 14, 12, 6, case)        # cuello
            tft.fill_rect(x - 6,  y - 20, 12, 6, tip)         # base de bala
            tft.fill_rect(x - 5,  y - 26, 10, 6, tip)         # ojiva (escalera)
            tft.fill_rect(x - 4,  y - 30, 8, 4, tip)
            tft.fill_rect(x - 3,  y - 34, 6, 4, tip)
            tft.fill_rect(x - 1,  y - 38, 2, 4, tip)          # punta
            tft.vline(x - 7, y, 22, _dim(255, 255, 255, 0.45))  # brillo
        else:
            tft.fill_rect(x - 31, y - 12, 5, 24, case)        # culote
            tft.fill_rect(x - 26, y - 10, 28, 20, case)       # cuerpo
            tft.fill_rect(x + 2,  y - 8, 6, 16, case)         # hombro+cuello
            tft.fill_rect(x + 8,  y - 6, 12, 12, tip)         # bala
            tft.fill_rect(x + 20, y - 4, 6, 8, tip)
            tft.fill_rect(x + 26, y - 2, 5, 4, tip)           # punta

    def _cartridge_row(self, alive):
        """3 cartuchos estáticos; durante la transición el del primer slot
        sale saltando con giro y el nuevo entra con fade-in."""
        tip = COPPER if alive else GREY
        case = BRASS if alive else GREY
        x0 = _CX - _SLOT_DX
        self._cartridge(_CX, _ROW_Y, tip, case)
        self._cartridge(_CX + _SLOT_DX, _ROW_Y, tip, case)

        if self._anim_left <= 0:
            self._cartridge(x0, _ROW_Y, tip, case)
            return

        k = _ANIM_FRAMES - self._anim_left        # 0 … _ANIM_FRAMES-1
        t = (k + 1) / _ANIM_FRAMES                # progreso 0..1
        self._anim_left -= 1

        # Saliente: salto arriba-izquierda; el "giro" se aproxima alternando
        # orientación vertical/horizontal cada 2 frames.
        jx = int(x0 - 50 * t)
        jy = int(_ROW_Y - 80 * t * (2.0 - t))
        if t < 0.85:                              # se desvanece al final
            self._cartridge(jx, jy, tip, case, horizontal=(k // 2) % 2 == 1)

        # Entrante: fade-in por niveles de brillo en el mismo slot
        lv = min(3, int(t * 4))
        if alive:
            self._cartridge(x0, _ROW_Y, _COPPER_LV[lv], _BRASS_LV[lv])
        else:
            self._cartridge(x0, _ROW_Y, GREY, GREY)

    def _spinner(self, cx, cy):
        """Dos flechas circulares girando juntas en el mismo sentido
        (horario): arcos y puntas derivan del mismo ángulo base."""
        r = 34
        for k in range(2):
            self._arrow_arc(cx, cy, r, self._spin_angle + k * 180, 130, WHITE)

    def _arrow_arc(self, cx, cy, r, start_deg, span_deg, color):
        tft = self.tft
        step = 6
        a = 0
        while a <= span_deg:
            rad = math.radians(start_deg + a)
            x = int(cx + r * math.cos(rad))
            y = int(cy + r * math.sin(rad))
            tft.ellipse(x, y, 3, 3, color, True)
            a += step
        # Punta en el extremo DELANTERO del arco (start+span va adelante al
        # crecer el ángulo → giro horario), apuntando en el sentido de giro.
        rad_end = math.radians(start_deg + span_deg)
        tip_x = cx + r * math.cos(rad_end)
        tip_y = cy + r * math.sin(rad_end)
        tang = math.radians(start_deg + span_deg + 90)   # tangente de avance
        for da in (-0.45, 0.45):
            bx = tip_x - 12 * math.cos(tang + da)
            by = tip_y - 12 * math.sin(tang + da)
            tft.line(int(tip_x), int(tip_y), int(bx), int(by), color)

    def _center_text(self, s, y, color, scale=2):
        """Texto 8×8 escalado por bloques (framebuf no escala nativo)."""
        import framebuf
        w = len(s) * 8
        buf = bytearray(w * 8 * 2)
        fb = framebuf.FrameBuffer(buf, w, 8, framebuf.RGB565)
        fb.fill(BLACK)
        fb.text(s, 0, 0, color)
        x0 = _CX - (w * scale) // 2
        tft = self.tft
        for yy in range(8):
            for xx in range(w):
                px = (buf[(yy * w + xx) * 2] << 8) | buf[(yy * w + xx) * 2 + 1]
                if px:
                    tft.fill_rect(x0 + xx * scale, y + yy * scale,
                                  scale, scale, color)

    # ── Render principal ────────────────────────────────────────────────
    def render(self, current, maximum, reloading=False, link_ok=True):
        tft = self.tft
        self._blink = not self._blink

        maximum = max(1, maximum)
        frac = current / maximum

        # Color del arco según nivel
        if current <= 0:
            arc_color = RED if self._blink else BLACK      # rojo parpadeante
        elif frac > 0.5:
            arc_color = GREEN
        elif frac >= 0.2:
            arc_color = YELLOW
        else:
            arc_color = RED

        # Fondo (flash naranja en disparo)
        if self._flash_frames > 0:
            tft.fill(color565(60, 25, 0))
            self._flash_frames -= 1
        else:
            tft.fill(BLACK)

        # Arco perimetral (arriba → abajo)
        self._arc(frac if current > 0 else 1.0, arc_color)

        if reloading:
            self._spin_angle = (self._spin_angle + 20) % 360
            self._spinner(_CX, _ROW_Y)
        else:
            self._cartridge_row(alive=current > 0)

        # Contador "actuales / máx"
        txt = "%d / %d" % (current, maximum)
        self._center_text(txt, 162, WHITE if current > 0 else RED, scale=3)

        # Estado del enlace ESPNow
        if not link_ok:
            self._center_text("SIN ENLACE", 202, GREY, scale=1)

        tft.show()

    def splash(self):
        tft = self.tft
        tft.fill(BLACK)
        self._arc(1.0, GREY)
        self._center_text("M2-DAQ", 100, WHITE, scale=3)
        self._center_text("esperando datos", 140, GREY, scale=1)
        tft.show()
