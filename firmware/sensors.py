# sensors.py — S1, S2, S3, ENC_H(A+B), ENC_V(A+B), Electroválvula (sin IMU)
# Interfaz pública:
#   init(), read() → dict, reset_encoders(),
#   valve_pulse(ms), fire_event(), reload_event()

import time
import micropython
import config
from machine import Pin

# ---------------------------------------------------------------------------
# Estado del módulo
# ---------------------------------------------------------------------------
_pin_s1   = None
_pin_s2   = None
_pin_s3   = None
_pin_eh_b = None
_pin_ev_b = None
_valve_pin = None

# Contadores de encoder en lista mutable — modificables desde ISR sin 'global'
_counters = [0, 0]           # [enc_h, enc_v]

# Métodos pre-enlazados para el hot-path de las ISR
_eh_b_val = None
_ev_b_val = None

# ---------------------------------------------------------------------------
# Máquina de estados de la válvula / conteo de balas
# ---------------------------------------------------------------------------
_s1_prev        = False
_s3_prev        = False
_rounds_fired   = 0
_valve_blocked  = False
_fire_event     = False      # disparo (real o manual) este ciclo → LED rojo + HID clic
_reload_event   = False      # recarga este ciclo (para LED naranja + tecla r)
_manual_shot    = False      # disparo manual este ciclo → HID clic forzado

# Recarga por sostenimiento de S1 (posible en cualquier momento, no solo bloqueada)
_s1_hold_start        = 0
_s1_reloaded_this_hold = False

# Pulso manual de válvula (comando 0xBB 0x01)
_pulse_until_ms = 0          # ticks_ms fin del pulso; 0 = sin pulso activo

# Ventana del indicador de recarga (spinner en el C3): 1 s tras recarga real
_reload_show_until = 0
RELOAD_SHOW_MS = 1000

# Overrides de sensores desde el host (ControlLink, comando 0xBB 0x02):
# se combinan con OR sobre la lectura física.
_ovr_enabled = False
_ovr_s1 = False
_ovr_s2 = False
_ovr_s3 = False


# ---------------------------------------------------------------------------
# ISR de encoders — @micropython.native (~3× más rápido)
# ---------------------------------------------------------------------------
@micropython.native
def _enc_h_isr(p):
    _counters[0] += 1 if (p.value() ^ _eh_b_val()) else -1


@micropython.native
def _enc_v_isr(p):
    _counters[1] += 1 if (p.value() ^ _ev_b_val()) else -1


# ---------------------------------------------------------------------------
# Pública: init()
# ---------------------------------------------------------------------------
def init():
    global _pin_s1, _pin_s2, _pin_s3, _pin_eh_b, _pin_ev_b
    global _eh_b_val, _ev_b_val, _valve_pin

    # Sensores digitales (activo-bajo → pull-up interno)
    _pin_s1 = Pin(config.PIN_S1, Pin.IN, Pin.PULL_UP)
    _pin_s2 = Pin(config.PIN_S2, Pin.IN, Pin.PULL_UP)
    _pin_s3 = Pin(config.PIN_S3, Pin.IN, Pin.PULL_UP)

    # Encoders cuadratura: IRQ en fase A, dirección por estado de fase B
    _pin_eh_b = Pin(config.PIN_ENC_H_B, Pin.IN, Pin.PULL_UP)
    _pin_ev_b = Pin(config.PIN_ENC_V_B, Pin.IN, Pin.PULL_UP)
    pin_eh_a  = Pin(config.PIN_ENC_H_A, Pin.IN, Pin.PULL_UP)
    pin_ev_a  = Pin(config.PIN_ENC_V_A, Pin.IN, Pin.PULL_UP)

    _eh_b_val = _pin_eh_b.value
    _ev_b_val = _pin_ev_b.value

    pin_eh_a.irq(trigger=Pin.IRQ_RISING | Pin.IRQ_FALLING, handler=_enc_h_isr)
    pin_ev_a.irq(trigger=Pin.IRQ_RISING | Pin.IRQ_FALLING, handler=_enc_v_isr)

    # Electroválvula — salida digital, arranca cerrada
    _valve_pin = Pin(config.PIN_VALVE_OUT, Pin.OUT, value=0)

    print("[sensors] Hardware inicializado (S1/S2/S3, ENC_H, ENC_V, válvula).")


# ---------------------------------------------------------------------------
# Pública: reset y eventos
# ---------------------------------------------------------------------------
def reset_encoders():
    _counters[0] = 0
    _counters[1] = 0


def fire_event():
    """True una sola vez por flanco ascendente de S3 (consumido al leer)."""
    global _fire_event
    e, _fire_event = _fire_event, False
    return e


def reload_event():
    """True una sola vez por recarga detectada (consumido al leer)."""
    global _reload_event
    e, _reload_event = _reload_event, False
    return e


def reload_active():
    """True mientras dura la ventana de 1 s tras una recarga efectiva
    (usado por espnow_tx para el spinner del C3)."""
    return time.ticks_diff(_reload_show_until, time.ticks_ms()) > 0


def inject_encoder(axis, delta):
    """ControlLink (cmd 0xBB 0x03/0x04): suma delta al contador real del
    encoder (0=H, 1=V), igual que si girara físicamente — así el mismo
    hid_mouse.update() mueve el mouse real por el mismo camino de código."""
    _counters[axis] += delta


def set_override(arg):
    """ControlLink (cmd 0xBB 0x02): bit3 = habilitado; bits0-2 = S1/S2/S3.
    Los valores forzados se combinan con OR sobre los sensores físicos."""
    global _ovr_enabled, _ovr_s1, _ovr_s2, _ovr_s3
    _ovr_enabled = bool(arg & 0x08)
    _ovr_s1 = bool(arg & 0x01)
    _ovr_s2 = bool(arg & 0x02)
    _ovr_s3 = bool(arg & 0x04)


def consume_manual_shot():
    """True una sola vez si el disparo de este ciclo fue por pulso manual
    (usado por main.py para forzar el clic HID, ya que no hay flanco de S3)."""
    global _manual_shot
    e, _manual_shot = _manual_shot, False
    return e


def _register_shot():
    """Contabiliza un disparo (real o manual): flag de evento + conteo +
    bloqueo de válvula si se agota el cargador."""
    global _rounds_fired, _valve_blocked, _fire_event
    _fire_event = True
    _rounds_fired += 1
    if _rounds_fired >= config.BULLET_MAGAZINE:
        _valve_blocked = True
        _valve_pin.value(0)


def valve_pulse(duration_ms):
    """Pulso manual de válvula (comando host).
    Actúa exactamente como un disparo real: cuenta la bala, dispara el
    evento (LED rojo + clic HID) y bloquea si se agota el cargador."""
    global _pulse_until_ms, _manual_shot
    if _valve_blocked:
        return
    _register_shot()
    _manual_shot = True
    if _valve_blocked:
        return                                   # este disparo agotó el cargador
    duration_ms = max(10, min(500, duration_ms))
    _pulse_until_ms = time.ticks_add(time.ticks_ms(), duration_ms)
    _valve_pin.value(1)


# ---------------------------------------------------------------------------
# Privada: tick de la máquina de estados de la válvula
# ---------------------------------------------------------------------------
def _valve_tick(s1, s3):
    global _rounds_fired, _valve_blocked, _s1_prev, _s3_prev
    global _reload_event, _pulse_until_ms, _reload_show_until
    global _s1_hold_start, _s1_reloaded_this_hold

    s1_rising  = s1 and not _s1_prev
    s1_falling = (not s1) and _s1_prev
    _s1_prev   = s1
    s3_rising  = s3 and not _s3_prev
    _s3_prev   = s3

    now = time.ticks_ms()
    if s1_rising:
        _s1_hold_start = now
        _s1_reloaded_this_hold = False
    if s1_falling:
        _s1_reloaded_this_hold = False

    # ── Recarga por sostenimiento de S1 (en cualquier momento) ────────
    if s1 and not _s1_reloaded_this_hold:
        if time.ticks_diff(now, _s1_hold_start) >= config.RELOAD_HOLD_MS:
            _rounds_fired  = 0
            _valve_blocked = False
            _reload_event  = True
            _s1_reloaded_this_hold = True
            _reload_show_until = time.ticks_add(now, RELOAD_SHOW_MS)

    # ── Estado bloqueado: válvula cerrada ─────────────────────────────
    if _valve_blocked:
        _valve_pin.value(0)
        _pulse_until_ms = 0
        return False

    # ── Operación normal: contar disparos por flanco S3 ──────────────
    if s3_rising:
        _register_shot()
        if _valve_blocked:
            _pulse_until_ms = 0
            return False

    # ── Pulso manual activo: mantiene válvula abierta hasta expirar ──
    if _pulse_until_ms:
        if time.ticks_diff(_pulse_until_ms, time.ticks_ms()) > 0:
            _valve_pin.value(1)
            return True
        _pulse_until_ms = 0

    # Válvula sigue a S3 directamente
    _valve_pin.value(1 if s3 else 0)
    return s3


# ---------------------------------------------------------------------------
# Pública: read() → dict canónico
# ---------------------------------------------------------------------------
def read():
    # GPIO=0 (pull-up activo) → sensor activo → True
    s1 = not _pin_s1.value()
    s2 = not _pin_s2.value()
    s3 = not _pin_s3.value()

    # ControlLink: la UI puede forzar sensores (OR con la lectura física)
    if _ovr_enabled:
        s1 = s1 or _ovr_s1
        s2 = s2 or _ovr_s2
        s3 = s3 or _ovr_s3

    valve = _valve_tick(s1, s3)

    return {
        "s1": s1, "s2": s2, "s3": s3,
        "valve": valve,
        "valve_blocked": _valve_blocked,
        "rounds_fired": _rounds_fired,
        "magazine": config.BULLET_MAGAZINE,
        "enc_h": _counters[0],
        "enc_v": _counters[1],
        "ts_ms": time.ticks_ms(),
    }
