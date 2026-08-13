# config.py — ESP32-C3 + pantalla GC9A01 1.28" (240×240 SPI)
# MAC del ESP32-S3 emisor y pines SPI de la pantalla.

# ---------------------------------------------------------------------------
# ESPNow — MAC del ESP32-S3 (emisor). b"\xff..." = aceptar broadcast.
# ---------------------------------------------------------------------------
S3_MAC = b"\xff\xff\xff\xff\xff\xff"

# ---------------------------------------------------------------------------
# Pines SPI pantalla GC9A01 (módulo ESP32-C3 con pantalla integrada)
# Ajustar según el módulo concreto.
# ---------------------------------------------------------------------------
SPI_ID     = 1
PIN_SCK    = 6
PIN_MOSI   = 7
PIN_DC     = 2
PIN_CS     = 10
PIN_RST    = 3
PIN_BL     = 11        # backlight; -1 si no existe
SPI_BAUD   = 40_000_000

# ---------------------------------------------------------------------------
# Valores por defecto antes de recibir el primer paquete
# ---------------------------------------------------------------------------
DEFAULT_MAX = 50

# Timeout sin datos ESPNow para considerar enlace perdido (ms)
LINK_TIMEOUT_MS = 5000
