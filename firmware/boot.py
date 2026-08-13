# boot.py — CPU 240 MHz · sin WiFi · protege main
# Se ejecuta antes que main.py en cada power-on / reset.

import sys
import machine
import esp

# Asegurar que /lib esté en el path (necesario para usb.device → HID)
if "/lib" not in sys.path:
    sys.path.append("/lib")

machine.freq(240_000_000)

# Silenciar mensajes internos del SO (reduce ruido en la UART serie)
esp.osdebug(None)

# El try/except evita que el ESP32 quede atrapado en un bucle de reset si
# main.py tiene un error de importación.
try:
    import main
except Exception as e:
    print("[boot] ERROR al importar main:", e)
