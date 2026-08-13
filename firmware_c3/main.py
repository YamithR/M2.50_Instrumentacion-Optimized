# main.py — ESP32-C3: recibe ESPNow desde el ESP32-S3 → actualiza display.
# Payload esperado: struct.pack(">HHB", balas_max, balas_actuales, flags)
#   flags bit0 = recarga efectiva reciente (ventana 1 s) → spinner — 5 bytes

import struct
import time
import network
import espnow
import config
from display import Display


def run():
    disp = Display()
    disp.splash()

    sta = network.WLAN(network.STA_IF)
    sta.active(True)
    try:
        sta.disconnect()
    except Exception:
        pass

    e = espnow.ESPNow()
    e.active(True)
    print("[c3] ESPNow RX listo. MAC propia:", sta.config("mac").hex())

    cur = config.DEFAULT_MAX
    mx = config.DEFAULT_MAX
    reloading = False
    last_rx = time.ticks_ms()
    have_data = False

    while True:
        # Recibir sin bloquear (timeout 0); drenar cola quedándonos con el último
        pkt = None
        while True:
            host, msg = e.recv(0)
            if msg is None:
                break
            if len(msg) == 5 and (config.S3_MAC == b"\xff\xff\xff\xff\xff\xff"
                                  or host == config.S3_MAC):
                pkt = msg
        if pkt is not None:
            new_mx, new_cur, flags = struct.unpack(">HHB", pkt)
            if have_data and new_cur < cur:
                disp.fire_animation()          # frame con cambio → animación
            cur, mx = new_cur, new_mx
            reloading = bool(flags & 0x01)
            last_rx = time.ticks_ms()
            have_data = True

        link_ok = time.ticks_diff(time.ticks_ms(), last_rx) < config.LINK_TIMEOUT_MS

        if have_data:
            disp.render(cur, mx, reloading, link_ok)
        else:
            disp.splash()

        time.sleep_ms(50)                      # ~20 FPS máx


run()
