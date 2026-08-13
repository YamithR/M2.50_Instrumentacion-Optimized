# config.py — Única fuente de verdad (pines, timings, constantes)
# Firmware ESP32-S3 — M2.50 Instrumentación Optimizada

# ---------------------------------------------------------------------------
# Temporización
# ---------------------------------------------------------------------------
LOOP_HZ         = 50                     # frecuencia del loop principal
PERIOD_MS       = 1000 // LOOP_HZ        # 20 ms (pre-calculado)

# ---------------------------------------------------------------------------
# Pines GPIO — ESP32-S3 DevKitC-1 v1.1, N16R8
# NOTA: GPIO 35/36/37 reservados para Flash/PSRAM — NO USAR.
# ---------------------------------------------------------------------------
PIN_S1          = 17   # S1_BLOQUEADO  (activo-bajo, pull-up interno) → recarga
PIN_S2          = 16   # S2_RETENEDOR  (activo-bajo, pull-up interno)
PIN_S3          = 15   # S3_VÁLVULA    (activo-bajo, pull-up interno) → cuenta bala
PIN_ENC_H_A     = 4    # Encoder horizontal fase A (IRQ)
PIN_ENC_H_B     = 5    # Encoder horizontal fase B (lectura en ISR)
PIN_ENC_V_A     = 6    # Encoder vertical fase A (IRQ)
PIN_ENC_V_B     = 7    # Encoder vertical fase B (lectura en ISR)
PIN_VALVE_OUT   = 12   # Salida digital: electroválvula
PIN_LED_RGB     = 48   # WS2812 Neopixel — indicador de estado de fases

# ---------------------------------------------------------------------------
# Encoders — rangos de cuentas
# ---------------------------------------------------------------------------
ENC_H_CNT_MIN   = -1000
ENC_H_CNT_MAX   =  1000
ENC_V_CNT_MIN   =  -500
ENC_V_CNT_MAX   =   500

# ---------------------------------------------------------------------------
# USB HID Mouse absoluto (encoder → puntero de pantalla)
# ---------------------------------------------------------------------------
HID_ENC_H_MIN   = ENC_H_CNT_MIN
HID_ENC_H_MAX   = ENC_H_CNT_MAX
HID_ENC_V_MIN   = ENC_V_CNT_MIN
HID_ENC_V_MAX   = ENC_V_CNT_MAX
HID_INVERT_Y    = True    # True = elevación → cursor arriba (Y decrece)
HID_CLICK_MS    = 60      # duración del clic izquierdo en milisegundos

# ---------------------------------------------------------------------------
# Control por conteo de balas
# ---------------------------------------------------------------------------
BULLET_MAGAZINE = 50      # disparos antes de bloquear la válvula (magazine_max)
RELOAD_HOLD_MS  = 2500    # S1 debe estar activo continuamente esto para recargar

# ---------------------------------------------------------------------------
# Protocolo binario — ESP32-S3 ↔ Script Python
# ---------------------------------------------------------------------------
FRAME_MAGIC     = 0xAA    # header de frame device → host (14 bytes)
CMD_MAGIC       = 0xBB    # header de comando host → device (3 bytes)
CMD_VALVE_PULSE = 0x01    # cmd: pulso válvula manual
CMD_SET_SENSORS = 0x02    # cmd: ControlLink — forzar sensores (bit3=on, bits0-2=S1/S2/S3)
HANDSHAKE       = b"\xAA\x55"   # handshake que envía el script por USB
HANDSHAKE_ACK   = b"\x55\xAA"   # respuesta del ESP32-S3

# ---------------------------------------------------------------------------
# Fases de arranque (segundos desde inicio)
# ---------------------------------------------------------------------------
PHASE1_USB_S    = 10      # 0–10 s escucha USB UART
PHASE2_BLE_S    = 40      # 10–40 s advertising BLE
BLE_NAME        = "M2-DAQ"

# ---------------------------------------------------------------------------
# ESPNow — hacia ESP32-C3 (pantalla GC9A01)
# ---------------------------------------------------------------------------
ESPNOW_PEER_MAC = b"\xff\xff\xff\xff\xff\xff"   # broadcast; fijar MAC del C3 si se conoce
ESPNOW_HZ       = 10      # frecuencia máxima de envío al C3

# ---------------------------------------------------------------------------
# LED RGB — colores (R, G, B) con brillo moderado
# ---------------------------------------------------------------------------
LED_OFF         = (0, 0, 0)
LED_VIOLET      = (40, 0, 60)     # inicializando
LED_BLUE        = (0, 0, 80)      # USB (Fase 1)
LED_YELLOW      = (60, 50, 0)     # BLE (Fase 2)
LED_GREEN       = (0, 70, 0)      # autónomo (Fase 3)
LED_RED         = (90, 0, 0)      # flash disparo (S3)
LED_ORANGE      = (80, 25, 0)     # flash recarga (S1)
FLASH_FIRE_MS   = 100
FLASH_RELOAD_MS = 300
BLINK_MS        = 500             # semiperiodo de parpadeo 1 Hz
