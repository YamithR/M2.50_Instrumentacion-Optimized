# transport.py — Capa de transporte: USB UART / ninguno.
# El host es el script Python (daq_app). El protocolo es binario:
#   device → host : frames de 14 bytes (ver protocol en README A.5)
#   host → device : comandos de 3 bytes (0xBB cmd arg)
#
# Modos: "none" | "usb"

import sys
import select
import config

MODE_NONE = "none"
MODE_USB  = "usb"

_mode      = MODE_NONE
_poll      = None
_stdin_buf = b""
_rx_cmds   = []          # comandos parseados pendientes


# ═══════════════════════════════════════════════════════════════════════════
# USB UART (consola USB-CDC del ESP32-S3, en paralelo con HID)
# ═══════════════════════════════════════════════════════════════════════════
def init_usb():
    """Prepara la escucha de handshake por USB UART (stdin binario)."""
    global _poll
    _poll = select.poll()
    _poll.register(sys.stdin, select.POLLIN)


def _usb_read_available():
    """Lee todos los bytes disponibles en stdin sin bloquear."""
    data = b""
    while _poll and _poll.poll(0):
        ch = sys.stdin.buffer.read(1)
        if not ch:
            break
        data += ch
    return data


def usb_check_handshake():
    """Escucha 0xAA 0x55. Si llega, responde 0x55 0xAA y activa modo USB."""
    global _stdin_buf, _mode
    _stdin_buf += _usb_read_available()
    idx = _stdin_buf.find(config.HANDSHAKE)
    if idx >= 0:
        _stdin_buf = _stdin_buf[idx + len(config.HANDSHAKE):]
        sys.stdout.buffer.write(config.HANDSHAKE_ACK)
        _mode = MODE_USB
        return True
    # Evitar crecimiento sin límite
    if len(_stdin_buf) > 64:
        _stdin_buf = _stdin_buf[-2:]
    return False


# ═══════════════════════════════════════════════════════════════════════════
# API común
# ═══════════════════════════════════════════════════════════════════════════
def mode():
    return _mode


def send(frame):
    """Envía un frame binario por el canal activo. Silencioso si no hay canal."""
    if _mode == MODE_USB:
        try:
            sys.stdout.buffer.write(frame)
        except Exception:
            pass


def _parse_cmds(buf):
    """Extrae comandos de 3 bytes (0xBB cmd arg) del buffer. Retorna resto."""
    while True:
        idx = buf.find(bytes([config.CMD_MAGIC]))
        if idx < 0:
            return b""
        buf = buf[idx:]
        if len(buf) < 3:
            return buf
        _rx_cmds.append((buf[1], buf[2]))
        buf = buf[3:]


def poll_commands():
    """Retorna lista de (cmd, arg) recibidos desde el host y vacía la cola."""
    global _stdin_buf, _rx_cmds
    if _mode == MODE_USB:
        _stdin_buf += _usb_read_available()
        _stdin_buf = _parse_cmds(_stdin_buf)
    cmds, _rx_cmds = _rx_cmds, []
    return cmds
