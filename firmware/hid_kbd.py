# hid_kbd.py — Keyboard USB HID: envía la tecla 'r' al detectar recarga (S1).
# Se integra con hid_mouse como interfaz adicional del dispositivo compuesto.
# Inicialización diferida: create_interface() → registrar en usb.device.get().init()

import time

_HID_REPORT_DESC = bytes([
    0x05, 0x01,        # Usage Page (Generic Desktop)
    0x09, 0x06,        # Usage (Keyboard)
    0xA1, 0x01,        # Collection (Application)
    0x05, 0x07,        #   Usage Page (Key Codes)
    0x19, 0xE0,        #   Usage Minimum (224)
    0x29, 0xE7,        #   Usage Maximum (231)
    0x15, 0x00,        #   Logical Minimum (0)
    0x25, 0x01,        #   Logical Maximum (1)
    0x75, 0x01,        #   Report Size (1)
    0x95, 0x08,        #   Report Count (8)
    0x81, 0x02,        #   Input (Data, Variable, Absolute) — modifiers
    0x95, 0x01,        #   Report Count (1)
    0x75, 0x08,        #   Report Size (8)
    0x81, 0x01,        #   Input (Constant) — reserved
    0x95, 0x06,        #   Report Count (6)
    0x75, 0x08,        #   Report Size (8)
    0x15, 0x00,        #   Logical Minimum (0)
    0x25, 0x65,        #   Logical Maximum (101)
    0x05, 0x07,        #   Usage Page (Key Codes)
    0x19, 0x00,        #   Usage Minimum (0)
    0x29, 0x65,        #   Usage Maximum (101)
    0x81, 0x00,        #   Input (Data, Array) — keycodes
    0xC0,              # End Collection
])

HID_KEY_R = 0x15

_kbd_iface = None


def create_interface():
    """Crea y retorna la interfaz HID keyboard. Retorna None si falla."""
    global _kbd_iface
    try:
        from usb.device.hid import HIDInterface
    except (ImportError, AttributeError):
        return None

    class _KbdInterface(HIDInterface):
        def __init__(self):
            super().__init__(
                _HID_REPORT_DESC,
                set_report_buf=None,
                protocol=0,
                interface_str="M2 Keyboard",
                interval_ms=8,
            )
            self._report = bytearray(8)

        def send_keys(self, keycodes):
            self._report[0] = 0x00
            self._report[1] = 0x00
            for i in range(6):
                self._report[2 + i] = keycodes[i] if i < len(keycodes) else 0x00
            self.send_report(self._report)

        def release_all(self):
            for i in range(8):
                self._report[i] = 0x00
            self.send_report(self._report)

    try:
        _kbd_iface = _KbdInterface()
        return _kbd_iface
    except Exception as e:
        print("[hid_kbd] Error creando interfaz:", e)
        return None


def send_reload():
    """Pulsa y suelta la tecla 'r' (recarga). No bloqueante salvo ~15 ms."""
    if _kbd_iface is None:
        return
    try:
        _kbd_iface.send_keys([HID_KEY_R])
        time.sleep_ms(15)
        _kbd_iface.release_all()
    except Exception:
        pass
