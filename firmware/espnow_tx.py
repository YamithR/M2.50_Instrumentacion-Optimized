# espnow_tx.py — Transmisor ESPNow → ESP32-C3 (pantalla GC9A01).
# Payload: struct.pack(">HHB", balas_max, balas_actuales, flags)  # 5 bytes
#   flags bit0 = recarga efectiva reciente (ventana de 1 s) → spinner del C3.
# SIEMPRE activo desde el inicio; envía solo cuando cambia el estado
# (con refresco periódico como keep-alive).

import struct
import time
import config

_esp        = None
_last_sent  = (-1, -1)
_last_ms    = 0
_MIN_GAP_MS = 1000 // config.ESPNOW_HZ
_KEEPALIVE_MS = 2000


def init():
    """Activa la interfaz STA (sin conectar a WiFi) y registra el peer."""
    global _esp
    try:
        import network
        import espnow
        sta = network.WLAN(network.STA_IF)
        sta.active(True)
        try:
            sta.disconnect()
        except Exception:
            pass
        _esp = espnow.ESPNow()
        _esp.active(True)
        _esp.add_peer(config.ESPNOW_PEER_MAC)
        print("[espnow] TX activo hacia", config.ESPNOW_PEER_MAC.hex())
        return True
    except Exception as e:
        print("[espnow] No disponible:", e)
        _esp = None
        return False


def update(magazine_max, rounds_fired, reload_active=False):
    """Envía (balas_max, balas_actuales, flags) si cambió o como keep-alive."""
    global _last_sent, _last_ms
    if _esp is None:
        return

    remaining = max(0, magazine_max - rounds_fired)
    now = time.ticks_ms()
    flags = 1 if reload_active else 0
    state = (magazine_max, remaining, flags)

    if state == _last_sent and time.ticks_diff(now, _last_ms) < _KEEPALIVE_MS:
        return
    if state != _last_sent and time.ticks_diff(now, _last_ms) < _MIN_GAP_MS:
        return

    try:
        _esp.send(config.ESPNOW_PEER_MAC,
                 struct.pack(">HHB", magazine_max, remaining, flags), False)
        _last_sent = state
        _last_ms = now
    except Exception:
        pass
