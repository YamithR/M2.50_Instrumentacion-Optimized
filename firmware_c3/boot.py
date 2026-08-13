# boot.py — Mínimo, protege main. ESP32-C3 + GC9A01.

import esp

esp.osdebug(None)

try:
    import main
except Exception as e:
    print("[boot] ERROR al importar main:", e)
