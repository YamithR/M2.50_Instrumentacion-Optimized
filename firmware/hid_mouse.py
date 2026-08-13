# hid_mouse.py — Mouse USB HID absoluto vía USB OTG del ESP32-S3.
# Requiere firmware MicroPython con soporte USB Device (TinyUSB) o el
# módulo usb-device-hid instalado (lib/usb/device incluido en este proyecto).
#
# Posición ABSOLUTA [0, 32767]:
#   ENC_H = 0 → X = 16383 (centro horizontal)
#   ENC_V = 0 → Y = 16383 (centro vertical)
#   Sobre-giro → satura en 0 o 32767 sin deriva.
# Flanco ascendente de S3 → clic izquierdo de HID_CLICK_MS ms.

import struct
import config

# ── Descriptor de reporte HID — Mouse absoluto 3 botones ──────────────────
_HID_REPORT_DESC = bytes([
    0x05, 0x01,        # Usage Page (Generic Desktop)
    0x09, 0x02,        # Usage (Mouse)
    0xA1, 0x01,        # Collection (Application)
    0x09, 0x01,        #   Usage (Pointer)
    0xA1, 0x00,        #   Collection (Physical)
    # Botones
    0x05, 0x09,        #     Usage Page (Button)
    0x19, 0x01,        #     Usage Minimum (1)
    0x29, 0x03,        #     Usage Maximum (3)
    0x15, 0x00,        #     Logical Minimum (0)
    0x25, 0x01,        #     Logical Maximum (1)
    0x95, 0x03,        #     Report Count (3)
    0x75, 0x01,        #     Report Size (1)
    0x81, 0x02,        #     Input (Data, Variable, Absolute)
    # Relleno (5 bits)
    0x95, 0x01, 0x75, 0x05, 0x81, 0x03,
    # X, Y absolutos 16 bits [0, 32767]
    0x05, 0x01,        #     Usage Page (Generic Desktop)
    0x09, 0x30,        #     Usage (X)
    0x09, 0x31,        #     Usage (Y)
    0x15, 0x00,        #     Logical Minimum (0)
    0x26, 0xFF, 0x7F,  #     Logical Maximum (32767)
    0x35, 0x00,        #     Physical Minimum (0)
    0x46, 0xFF, 0x7F,  #     Physical Maximum (32767)
    0x75, 0x10,        #     Report Size (16)
    0x95, 0x02,        #     Report Count (2)
    0x81, 0x02,        #     Input (Data, Variable, Absolute)
    0xC0,              #   End Collection
    0xC0,              # End Collection
])

_ABS_MAX = 32767

_hid_iface    = None
_prev_s3      = False
_click_frames = 0
_CLICK_FRAMES = max(1, round(config.HID_CLICK_MS / config.PERIOD_MS))


def _map_abs(cnt, cnt_min, cnt_max):
    if cnt <= cnt_min:
        return 0
    if cnt >= cnt_max:
        return _ABS_MAX
    return int((cnt - cnt_min) / (cnt_max - cnt_min) * _ABS_MAX)


def init():
    """Registra el dispositivo HID compuesto (mouse + teclado).
    Retorna True si tiene éxito; el sistema sigue funcionando sin HID."""
    global _hid_iface

    import sys
    if "/lib" not in sys.path:
        sys.path.append("/lib")

    try:
        import usb.device
        from usb.device.hid import HIDInterface
    except ImportError as e:
        print("[hid] USB HID desactivado — falta el módulo 'usb':", e)
        print("[hid] Verifica que /lib/usb/device/{__init__,core,hid}.py estén")
        print("[hid] en el ESP32 (usa deploy_s3.py) y que el firmware tenga")
        print("[hid] machine.USBDevice (build estándar ESP32_GENERIC_S3 >= 1.23).")
        return False
    except AttributeError as e:
        print("[hid] USB HID desactivado — firmware sin machine.USBDevice:", e)
        return False

    class _AbsMouse(HIDInterface):
        def __init__(self):
            super().__init__(
                _HID_REPORT_DESC,
                set_report_buf=None,
                protocol=0,
                interface_str="M2 Abs Mouse",
                interval_ms=8,
            )
            self._report = bytearray(5)

        def send_abs(self, buttons, x, y):
            struct.pack_into('<BHH', self._report, 0, buttons, x, y)
            self.send_report(self._report)

    try:
        iface_mouse = _AbsMouse()
        itfs = [iface_mouse]

        try:
            import hid_kbd
            iface_kbd = hid_kbd.create_interface()
            if iface_kbd is not None:
                itfs.append(iface_kbd)
        except Exception:
            pass

        usb.device.get().init(*itfs, builtin_driver=True)
        _hid_iface = iface_mouse
        print("[hid] HID compuesto activo (mouse%s)." %
              (" + teclado" if len(itfs) > 1 else ""))
        return True
    except Exception as e:
        print("[hid] Error inicializando HID:", e)
        _hid_iface = None
        return False


def update(enc_h, enc_v, s3, extra_click=False):
    """Envía reporte HID absoluto. Llamar a 50 Hz desde el loop principal.
    extra_click: fuerza un clic aunque S3 no tenga flanco (pulso manual)."""
    global _prev_s3, _click_frames

    if (s3 and not _prev_s3) or extra_click:
        _click_frames = _CLICK_FRAMES
    _prev_s3 = s3

    buttons = 0x01 if _click_frames > 0 else 0x00
    if _click_frames > 0:
        _click_frames -= 1

    if _hid_iface is None:
        return

    x = _map_abs(enc_h, config.HID_ENC_H_MIN, config.HID_ENC_H_MAX)
    y = _map_abs(enc_v, config.HID_ENC_V_MIN, config.HID_ENC_V_MAX)
    if config.HID_INVERT_Y:
        y = _ABS_MAX - y

    try:
        _hid_iface.send_abs(buttons, x, y)
    except Exception:
        pass
