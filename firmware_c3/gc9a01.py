# gc9a01.py — Driver SPI nativo para GC9A01 (240×240 round IPS), desde cero.
# Framebuffer completo RGB565 en RAM (115 200 bytes) + show() por SPI.

import time
import framebuf
from machine import Pin, SPI
from micropython import const

_SWRESET = const(0x01)
_SLPOUT  = const(0x11)
_INVON   = const(0x21)
_DISPON  = const(0x29)
_CASET   = const(0x2A)
_RASET   = const(0x2B)
_RAMWR   = const(0x2C)
_MADCTL  = const(0x36)
_COLMOD  = const(0x3A)

WIDTH  = const(240)
HEIGHT = const(240)

# Secuencia de inicialización del controlador GC9A01
_INIT_SEQ = (
    (0xEF, b""),
    (0xEB, b"\x14"),
    (0xFE, b""), (0xEF, b""),
    (0xEB, b"\x14"),
    (0x84, b"\x40"),
    (0x85, b"\xFF"),
    (0x86, b"\xFF"),
    (0x87, b"\xFF"),
    (0x88, b"\x0A"),
    (0x89, b"\x21"),
    (0x8A, b"\x00"),
    (0x8B, b"\x80"),
    (0x8C, b"\x01"),
    (0x8D, b"\x01"),
    (0x8E, b"\xFF"),
    (0x8F, b"\xFF"),
    (0xB6, b"\x00\x00"),
    (_MADCTL, b"\x48"),
    (_COLMOD, b"\x05"),                      # 16 bpp RGB565
    (0x90, b"\x08\x08\x08\x08"),
    (0xBD, b"\x06"),
    (0xBC, b"\x00"),
    (0xFF, b"\x60\x01\x04"),
    (0xC3, b"\x13"),
    (0xC4, b"\x13"),
    (0xC9, b"\x22"),
    (0xBE, b"\x11"),
    (0xE1, b"\x10\x0E"),
    (0xDF, b"\x21\x0C\x02"),
    (0xF0, b"\x45\x09\x08\x08\x26\x2A"),
    (0xF1, b"\x43\x70\x72\x36\x37\x6F"),
    (0xF2, b"\x45\x09\x08\x08\x26\x2A"),
    (0xF3, b"\x43\x70\x72\x36\x37\x6F"),
    (0xED, b"\x1B\x0B"),
    (0xAE, b"\x77"),
    (0xCD, b"\x63"),
    (0x70, b"\x07\x07\x04\x0E\x0F\x09\x07\x08\x03"),
    (0xE8, b"\x34"),
    (0x62, b"\x18\x0D\x71\xED\x70\x70\x18\x0F\x71\xEF\x70\x70"),
    (0x63, b"\x18\x11\x71\xF1\x70\x70\x18\x13\x71\xF3\x70\x70"),
    (0x64, b"\x28\x29\xF1\x01\xF1\x00\x07"),
    (0x66, b"\x3C\x00\xCD\x67\x45\x45\x10\x00\x00\x00"),
    (0x67, b"\x00\x3C\x00\x00\x00\x01\x54\x10\x32\x98"),
    (0x74, b"\x10\x85\x80\x00\x00\x4E\x00"),
    (0x98, b"\x3E\x07"),
    (0x35, b""),
    (_INVON, b""),
)


def color565(r, g, b):
    """(r, g, b) 0–255 → RGB565 big-endian tal como lo espera el panel."""
    c = ((r & 0xF8) << 8) | ((g & 0xFC) << 3) | (b >> 3)
    return ((c & 0xFF) << 8) | (c >> 8)      # swap para framebuf + SPI MSB


class GC9A01(framebuf.FrameBuffer):
    def __init__(self, spi_id, sck, mosi, dc, cs, rst, bl=-1, baud=40_000_000):
        self._spi = SPI(spi_id, baudrate=baud, polarity=0, phase=0,
                        sck=Pin(sck), mosi=Pin(mosi))
        self._dc = Pin(dc, Pin.OUT, value=0)
        self._cs = Pin(cs, Pin.OUT, value=1)
        self._rst = Pin(rst, Pin.OUT, value=1)
        self._bl = Pin(bl, Pin.OUT, value=1) if bl >= 0 else None

        self._buf = bytearray(WIDTH * HEIGHT * 2)
        super().__init__(self._buf, WIDTH, HEIGHT, framebuf.RGB565)

        self._hw_reset()
        self._init_panel()

    # ── Bajo nivel ─────────────────────────────────────────────────────
    def _hw_reset(self):
        self._rst.value(1)
        time.sleep_ms(10)
        self._rst.value(0)
        time.sleep_ms(10)
        self._rst.value(1)
        time.sleep_ms(120)

    def _cmd(self, cmd, data=b""):
        self._cs.value(0)
        self._dc.value(0)
        self._spi.write(bytes([cmd]))
        if data:
            self._dc.value(1)
            self._spi.write(data)
        self._cs.value(1)

    def _init_panel(self):
        for cmd, data in _INIT_SEQ:
            self._cmd(cmd, data)
        self._cmd(_SLPOUT)
        time.sleep_ms(120)
        self._cmd(_DISPON)
        time.sleep_ms(20)

    def _set_window(self, x0, y0, x1, y1):
        self._cmd(_CASET, bytes([x0 >> 8, x0 & 0xFF, x1 >> 8, x1 & 0xFF]))
        self._cmd(_RASET, bytes([y0 >> 8, y0 & 0xFF, y1 >> 8, y1 & 0xFF]))

    # ── API pública ────────────────────────────────────────────────────
    def backlight(self, on):
        if self._bl is not None:
            self._bl.value(1 if on else 0)

    def show(self):
        """Vuelca el framebuffer completo al panel."""
        self._set_window(0, 0, WIDTH - 1, HEIGHT - 1)
        self._cs.value(0)
        self._dc.value(0)
        self._spi.write(bytes([_RAMWR]))
        self._dc.value(1)
        self._spi.write(self._buf)
        self._cs.value(1)
