# main.py — Orquestador: secuencia de arranque con LED RGB + loop principal.
#
# FASE 1 [0–10 s]  : AZUL parpadeo — escucha handshake USB (0xAA 0x55)
# FASE 2 [10–40 s] : AMARILLO parpadeo — BLE advertising "M2-DAQ"
# FASE 3 [>40 s]   : VERDE fijo — autónomo (HID + ESPNow, sin host externo)
# Eventos: ROJO flash 100 ms (disparo S3) · NARANJA flash 300 ms (recarga S1)
# HID y ESPNow SIEMPRE activos, independientes del transporte.

import struct
import time
import config
import sensors
import transport
import espnow_tx
import hid_mouse
import hid_kbd

# ───────────────────────────── LED RGB (WS2812) ────────────────────────────
_np = None


def _led_init():
    global _np
    try:
        from machine import Pin
        import neopixel
        _np = neopixel.NeoPixel(Pin(config.PIN_LED_RGB), 1)
    except Exception as e:
        print("[led] WS2812 no disponible:", e)


def _led(color):
    if _np is not None:
        _np[0] = color
        _np.write()


# ───────────────────────── Empaquetado de frames ───────────────────────────
_frame = bytearray(14)


def _pack_frame(d):
    flags = ((1 if d["s1"] else 0)
             | (2 if d["s2"] else 0)
             | (4 if d["s3"] else 0)
             | (8 if d["valve_blocked"] else 0)
             | (16 if d["valve"] else 0))
    eh = max(config.ENC_H_CNT_MIN, min(config.ENC_H_CNT_MAX, d["enc_h"]))
    ev = max(config.ENC_V_CNT_MIN, min(config.ENC_V_CNT_MAX, d["enc_v"]))
    struct.pack_into(">BIBhhHB", _frame, 0,
                     config.FRAME_MAGIC,
                     d["ts_ms"] & 0xFFFFFFFF,
                     flags, eh, ev,
                     d["rounds_fired"] & 0xFFFF,
                     d["magazine"] & 0xFF)
    chk = 0
    for i in range(13):
        chk ^= _frame[i]
    _frame[13] = chk
    return _frame


# ───────────────────────────── Programa principal ──────────────────────────
def run():
    _led_init()
    _led(config.LED_VIOLET)                 # 🟣 inicializando

    sensors.init()
    hid_mouse.init()                        # HID mouse + teclado (compuesto)
    espnow_tx.init()                        # ESPNow: siempre activo
    transport.init_usb()

    t0 = time.ticks_ms()
    ble_started = False
    base_color = None                       # color de fondo actual del LED
    flash_until = 0
    flash_color = None

    while True:
        loop_start = time.ticks_ms()
        elapsed_s = time.ticks_diff(loop_start, t0) / 1000
        blink_on = (loop_start // config.BLINK_MS) % 2 == 0

        # ── Comandos del host — ANTES de leer sensores para que un pulso
        # manual se contabilice, actúe y aparezca en el frame de este mismo
        # ciclo (mismo efecto que un disparo real) ──────────────────────
        for cmd, arg in transport.poll_commands():
            if cmd == config.CMD_VALVE_PULSE:
                sensors.valve_pulse(arg * 10)           # decenas de ms
            elif cmd == config.CMD_SET_SENSORS:
                sensors.set_override(arg)               # ControlLink

        # ── Gestión de fases / transporte ──────────────────────────────
        mode = transport.mode()
        if mode == transport.MODE_USB:
            base_color = config.LED_BLUE                    # 🔵 fijo
        elif mode == transport.MODE_BLE:
            base_color = config.LED_YELLOW                  # 🟡 fijo
        elif elapsed_s < config.PHASE1_USB_S:
            # FASE 1: escucha USB
            base_color = config.LED_BLUE if blink_on else config.LED_OFF
            if transport.usb_check_handshake():
                print("[main] Handshake USB — modo USB binario activo.")
        elif elapsed_s < config.PHASE2_BLE_S:
            # FASE 2: BLE advertising (el handshake USB sigue aceptándose)
            if not ble_started:
                ble_started = transport.start_ble()
            base_color = config.LED_YELLOW if blink_on else config.LED_OFF
            transport.usb_check_handshake()
        else:
            # FASE 3: autónomo
            if ble_started:
                transport.stop_ble()
                ble_started = False
                print("[main] Fase 3 — operación autónoma HID.")
            base_color = config.LED_GREEN                   # 🟢 fijo

        # ── Sensores + HID (siempre activos) ───────────────────────────
        d = sensors.read()
        manual_shot = sensors.consume_manual_shot()
        hid_mouse.update(d["enc_h"], d["enc_v"], d["s3"], extra_click=manual_shot)

        # ── Eventos → flashes LED + tecla r ────────────────────────────
        if sensors.fire_event():
            flash_color = config.LED_RED                    # 🔴 100 ms
            flash_until = time.ticks_add(loop_start, config.FLASH_FIRE_MS)
        if sensors.reload_event():
            flash_color = config.LED_ORANGE                 # 🟠 300 ms
            flash_until = time.ticks_add(loop_start, config.FLASH_RELOAD_MS)
            hid_kbd.send_reload()

        # ── ESPNow → ESP32-C3 (siempre activo) ─────────────────────────
        espnow_tx.update(d["magazine"], d["rounds_fired"], sensors.reload_active())

        # ── Transmisión binaria hacia el host ───────────────────────────
        if transport.mode() != transport.MODE_NONE:
            transport.send(_pack_frame(d))

        # ── LED: flash prioritario sobre color base ────────────────────
        if flash_color and time.ticks_diff(flash_until, loop_start) > 0:
            _led(flash_color)
        else:
            flash_color = None
            _led(base_color)

        # ── Cadencia 50 Hz ─────────────────────────────────────────────
        busy = time.ticks_diff(time.ticks_ms(), loop_start)
        if busy < config.PERIOD_MS:
            time.sleep_ms(config.PERIOD_MS - busy)


run()
