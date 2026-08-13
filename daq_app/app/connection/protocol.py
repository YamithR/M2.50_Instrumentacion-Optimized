# protocol.py — Parser de frames binarios de 14 bytes (ESP32-S3 → host)
# y constructor de comandos de control (host → ESP32-S3).
#
# Frame (14 bytes, big-endian):
#   Byte  0     : 0xAA  magic
#   Bytes 1–4   : uint32 timestamp_ms
#   Byte  5     : uint8  flags (bit0=S1, bit1=S2, bit2=S3,
#                                bit3=valve_blocked, bit4=valve activa)
#   Bytes 6–7   : int16  enc_h
#   Bytes 8–9   : int16  enc_v
#   Bytes 10–11 : uint16 rounds_fired
#   Byte  12    : uint8  magazine_max
#   Byte  13    : uint8  checksum (XOR bytes 0–12)

import struct
from dataclasses import dataclass

FRAME_MAGIC = 0xAA
FRAME_SIZE = 14
CMD_MAGIC = 0xBB
CMD_VALVE_PULSE = 0x01
CMD_SET_SENSORS = 0x02
CMD_ENC_H = 0x03
CMD_ENC_V = 0x04
HANDSHAKE = b"\xAA\x55"
HANDSHAKE_ACK = b"\x55\xAA"

_STRUCT = struct.Struct(">BIBhhHB")


@dataclass
class Frame:
    ts_ms: int
    s1: bool
    s2: bool
    s3: bool
    valve_blocked: bool
    valve: bool
    enc_h: int
    enc_v: int
    rounds_fired: int
    magazine_max: int

    @property
    def rounds_left(self) -> int:
        return max(0, self.magazine_max - self.rounds_fired)


def checksum(data: bytes) -> int:
    chk = 0
    for b in data:
        chk ^= b
    return chk


def parse_frame(raw: bytes) -> Frame | None:
    """Parsea 14 bytes. Retorna None si magic o checksum son inválidos."""
    if len(raw) != FRAME_SIZE or raw[0] != FRAME_MAGIC:
        return None
    if checksum(raw[:13]) != raw[13]:
        return None
    _, ts_ms, flags, enc_h, enc_v, rounds, mag = _STRUCT.unpack(raw[:13])
    return Frame(
        ts_ms=ts_ms,
        s1=bool(flags & 0x01),
        s2=bool(flags & 0x02),
        s3=bool(flags & 0x04),
        valve_blocked=bool(flags & 0x08),
        valve=bool(flags & 0x10),
        enc_h=enc_h,
        enc_v=enc_v,
        rounds_fired=rounds,
        magazine_max=mag,
    )


class FrameParser:
    """Acumula bytes de un stream y extrae frames válidos de 14 bytes."""

    def __init__(self):
        self._buf = bytearray()

    def feed(self, data: bytes) -> list[Frame]:
        self._buf.extend(data)
        frames = []
        while True:
            idx = self._buf.find(bytes([FRAME_MAGIC]))
            if idx < 0:
                self._buf.clear()
                break
            if idx > 0:
                del self._buf[:idx]
            if len(self._buf) < FRAME_SIZE:
                break
            frame = parse_frame(bytes(self._buf[:FRAME_SIZE]))
            if frame is None:
                del self._buf[0]        # magic falso → re-sincronizar
                continue
            del self._buf[:FRAME_SIZE]
            frames.append(frame)
        return frames


def build_valve_pulse(duration_ms: int) -> bytes:
    """Comando 0xBB 0x01 <decenas de ms> — pulso manual de válvula."""
    tens = max(1, min(50, round(duration_ms / 10)))
    return bytes([CMD_MAGIC, CMD_VALVE_PULSE, tens])


def build_sensor_override(s1: bool, s2: bool, s3: bool, enable: bool) -> bytes:
    """Comando 0xBB 0x02 <arg> — ControlLink: fuerza sensores físicos.
    arg: bit0=S1, bit1=S2, bit2=S3, bit3=override habilitado."""
    arg = ((1 if s1 else 0) | (2 if s2 else 0) | (4 if s3 else 0)
           | (8 if enable else 0))
    return bytes([CMD_MAGIC, CMD_SET_SENSORS, arg])


def build_encoder_delta(axis: str, delta: int) -> bytes:
    """Comando 0xBB 0x03/0x04 <arg> — ControlLink: inyecta delta (-128..127)
    al contador real del encoder H o V. arg = delta + 128 (sin signo)."""
    cmd = CMD_ENC_H if axis == "h" else CMD_ENC_V
    delta = max(-128, min(127, delta))
    return bytes([CMD_MAGIC, cmd, delta + 128])
