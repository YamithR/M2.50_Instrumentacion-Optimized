# M2.50 Instrumentación Optimizada

Sistema de adquisición de datos (DAQ) optimizado para el sistema de arma M2.50, eliminando funcionalidades decorativas y conservando únicamente los componentes esenciales con máxima eficiencia.

---

## Visión General

```
[ESP32-S3]  ──ESPNow──►  [ESP32-C3 + GC9A01 1.28"]
     │
     ├── USB UART (binario empaquetado)
     └── BLE UART
          │
     [Script Python / PySide6]
          ├── Dashboard tiempo real
          ├── Gráficas encoders / sensores / balas
          └── Pestaña simulador intercambiable
```

---

## MÓDULO A — Firmware ESP32-S3 (MicroPython Optimizado)

### A.1 Componentes eliminados del proyecto de referencia

| Archivo / Componente | Motivo |
|---|---|
| `server.py` | WiFi + WebSocket + HTTP → eliminado completo |
| `gy89_driver.py` | Giroscopio / IMU → suprimido |
| `web/` completo | Dashboard HTML/JS/CSS → irrelevante |
| `lib/usb/device/core.py` / `hid.py` | Se **conservan** — HID sigue activo |

**`hid_mouse.py` y `hid_kbd.py` se conservan y mantienen activos en todo momento.**
- Encoders ENC_H + ENC_V → movimiento absoluto del mouse HID
- S3 (válvula / disparo) → clic HID
- S1 (recarga) → tecla `r` HID
- El script Python es una capa de **depuración paralela**, no reemplaza el HID

### A.2 Estructura de archivos del firmware

```
firmware/
├── boot.py          # CPU 240 MHz · sin WiFi · protege main
├── config.py        # Única fuente de verdad (pines, timings, constantes)
├── main.py          # Orquestador secuencia de arranque + loop principal
├── sensors.py       # S1, S2, S3, ENC_H(A+B), ENC_V(A+B), Electroválvula
├── transport.py     # Capa de transporte: USB UART / BLE / ninguno
├── espnow_tx.py     # Transmisor ESPNow → ESP32-C3
├── hid_mouse.py     # USB HID mouse absoluto (encoders)
├── hid_kbd.py       # USB HID teclado (recarga → tecla r)
└── lib/usb/device/
    ├── core.py
    └── hid.py
```

### A.3 Secuencia de arranque con LED RGB (GPIO 48 — WS2812)

```
boot.py  ─→  CPU 240 MHz, silencia logs

main.py:
  LED: 🟣 VIOLETA fijo — inicializando hardware (sensors, HID, ESPNow)

  ┌─ FASE 1: [0 – 10 s] ─────────────────────────────────────┐
  │  LED: 🔵 AZUL parpadeante (1 Hz)                         │
  │  Escucha USB UART esperando handshake del script Python   │
  │  Si recibe handshake → LED: 🔵 AZUL fijo                 │
  │                         modo USB binario activo           │
  │                         HID sigue activo                  │
  │                         salta FASE 2                      │
  └───────────────────────────────────────────────────────────┘
  ┌─ FASE 2: [10 – 40 s] ────────────────────────────────────┐
  │  LED: 🟡 AMARILLO parpadeante (1 Hz)                     │
  │  Activa BLE advertising ("M2-DAQ")                       │
  │  Si conecta cliente BLE → LED: 🟡 AMARILLO fijo          │
  │                            modo BLE binario activo        │
  │                            HID sigue activo               │
  └───────────────────────────────────────────────────────────┘
  ┌─ FASE 3: [> 40 s sin conexión externa] ──────────────────┐
  │  LED: 🟢 VERDE fijo                                      │
  │  BLE apagado                                             │
  │  HID activo (encoders=mouse, S3=clic, S1=tecla r)        │
  │  ESPNow activo → ESP32-C3                                │
  │  Loop de sensores continuo, sin transmisión externa      │
  └───────────────────────────────────────────────────────────┘

  Evento especial:
  LED: 🔴 ROJO flash (100 ms) en cada disparo detectado (S3)
  LED: 🟠 NARANJA flash (300 ms) al recargar (S1)

  ESPNow hacia ESP32-C3: SIEMPRE activo desde el inicio
```

**Tabla resumen LED RGB:**

| Color | Estado |
|---|---|
| 🟣 Violeta fijo | Inicializando |
| 🔵 Azul parpadeo | Esperando USB (Fase 1) |
| 🔵 Azul fijo | Conectado por USB |
| 🟡 Amarillo parpadeo | Advertising BLE (Fase 2) |
| 🟡 Amarillo fijo | Conectado por BLE |
| 🟢 Verde fijo | Operación autónoma HID (Fase 3) |
| 🔴 Rojo flash | Disparo detectado (S3) |
| 🟠 Naranja flash | Recarga detectada (S1) |

### A.4 Sensores y pines (config.py)

| Señal | GPIO | Tipo | Descripción |
|---|---|---|---|
| S1 | 17 | Digital IN pull-up | Cerrojo bloqueado → recarga |
| S2 | 16 | Digital IN pull-up | Cerrojo retenido |
| S3 | 15 | Digital IN pull-up | Válvula gas → cuenta bala |
| ENC_H_A | 4 | IRQ rising | Encoder horizontal (azimut) |
| ENC_H_B | 5 | GPIO read en ISR | Encoder horizontal dirección |
| ENC_V_A | 6 | IRQ rising | Encoder vertical (elevación) |
| ENC_V_B | 7 | GPIO read en ISR | Encoder vertical dirección |
| VALVE_OUT | 12 | Digital OUT | Electroválvula |
| LED_RGB | 48 | WS2812 Neopixel | Indicador de estado de fases |

### A.5 Protocolo binario — ESP32-S3 → Script Python (14 bytes/frame)

```
Byte  0      : 0xAA  (magic header)
Bytes 1–4    : uint32  timestamp_ms  (ms desde boot)
Byte  5      : uint8   flags         (bit0=S1, bit1=S2, bit2=S3, bit3=valve_blocked)
Bytes 6–7    : int16   enc_h         (-1000 a +1000)
Bytes 8–9    : int16   enc_v         (-500  a +500)
Bytes 10–11  : uint16  rounds_fired  (0 a 65535)
Byte  12     : uint8   magazine_max  (configurable, ej. 50)
Byte  13     : uint8   checksum      (XOR bytes 0–12)

Total: 14 bytes por frame @ 50 Hz = 700 bytes/s
```

**Protocolo de control — Script Python → ESP32-S3 (3 bytes/comando):**

```
Byte 0: 0xBB  (magic comando host→device)
Byte 1: 0x01  (cmd: pulso válvula manual)
Byte 2: uint8 duración en decenas de ms  (1=10ms, 5=50ms, 50=500ms)
```

### A.6 ESPNow payload — ESP32-S3 → ESP32-C3

```python
struct.pack(">HH", balas_max, balas_actuales)  # 4 bytes
```

---

## MÓDULO B — Firmware ESP32-C3 + Pantalla GC9A01 1.28" (MicroPython, desde cero)

### B.1 Hardware objetivo

| Componente | Especificación |
|---|---|
| MCU | ESP32-C3 integrado en módulo de pantalla |
| Pantalla | Round IPS 1.28" GC9A01, 240×240 px, SPI |
| Comunicación entrante | ESPNow desde ESP32-S3 |
| Datos recibidos | `balas_max` (uint16) + `balas_actuales` (uint16) |

### B.2 Estructura de archivos

```
firmware_c3/
├── boot.py          # Mínimo, protege main
├── config.py        # MAC del ESP32-S3, pines SPI pantalla
├── main.py          # Recibe ESPNow → actualiza display
├── gc9a01.py        # Driver SPI nativo para GC9A01 (desde cero)
└── display.py       # Motor gráfico: animación balística + fade circular
```

### B.3 Interfaz gráfica (240×240 círculo)

```
┌─────────────────────────────────────────┐
│         Pantalla circular 1.28"         │
│                                         │
│    ╔═══════════════════════════╗         │
│    ║  Borde arco RGB dinámico  ║         │
│    ║   (fade-out ↓ por balas)  ║         │
│    ║                           ║         │
│    ║     ícono bala            ║         │
│    ║       animado             ║         │
│    ║                           ║         │
│    ║       32 / 50             ║         │
│    ║   (actuales / máx)        ║         │
│    ╚═══════════════════════════╝         │
└─────────────────────────────────────────┘
```

**Lógica visual del borde circular:**

- El borde se divide en arco completo (360°) = cargador lleno
- A medida que bajan las balas, el arco se reduce desde **abajo hacia arriba** (fade-out vertical descendente)
- Animación de disparo: flash de color + vibración del ícono bala en cada frame recibido con cambio
- Escala de colores del arco:
  - Verde (> 50% balas restantes)
  - Amarillo (20% – 50%)
  - Rojo (< 20%)
  - Rojo parpadeante (0 balas — cargador vacío)

---

## MÓDULO C — Script Python / PySide6

### C.1 Estructura de archivos

```
daq_app/
├── main.py
├── requirements.txt
└── app/
    ├── window.py              # Ventana principal
    ├── connection/
    │   ├── usb_handler.py     # Detección y lectura UART (pyserial)
    │   ├── ble_handler.py     # Conexión BLE (bleak, asyncio)
    │   └── protocol.py        # Parser frames binarios de 14 bytes
    ├── views/
    │   ├── dashboard.py       # Vista principal datos en vivo
    │   ├── charts_view.py     # Gráficas encoders H/V en tiempo real (pyqtgraph)
    │   ├── sensors_panel.py   # LEDs virtuales S1/S2/S3 + válvula
    │   ├── ammo_panel.py      # Contador balas visual + botón pulso válvula
    │   └── sim_window.py      # Ventana flotante simulador
    └── simulator/
        ├── sim_engine.py      # Máquina de estados real (S1/S2/S3 + encoders)
        └── sim_controls.py    # Sliders y controles interactivos
```

### C.2 Dependencias Python

```
PySide6          # GUI principal
pyqtgraph        # Gráficas de alto rendimiento integradas en Qt
pyserial         # Comunicación USB UART
bleak            # BLE asyncio (cross-platform)
```

### C.3 Layout del Dashboard principal

```
┌──────────────────────────────────────────────────────────────┐
│  M2.50 DAQ  │ 🔴 Desconectado ▼ COM3  [Conectar] [Simular]  │
├────────────────────────┬─────────────────────────────────────┤
│  SENSORES              │  GRÁFICAS TIEMPO REAL               │
│                        │                                     │
│  ● S1  [BLOQUEADO]     │  ENC_H ───────────────────┐         │
│  ● S2  [RETENEDOR]     │       ~~~~~~~~~~~~~~~      │         │
│  ● S3  [VÁLVULA]       │  ENC_V ───────────────────┘         │
│                        │                                     │
│  ELECTROVÁLVULA        │  S1/S2/S3 (timeline binario)        │
│  Estado: [■ BLOQUEADA] │  ▁▁▁▁██▁▁▁██▁▁▁▁▁▁▁▁▁▁▁▁▁▁         │
│  [⚡ PULSO MANUAL]     │                                     │
│  Duración: [▓▓░░] 50ms │  ENC_H: +312°  ENC_V: -18°         │
│                        │  Hz: 50  Latencia: 2ms             │
│  BALAS                 ├─────────────────────────────────────┤
│  ████████░░ 32/50      │                                     │
└────────────────────────┴─────────────────────────────────────┘
```

**Botón PULSO MANUAL (Electroválvula):**
- Envía comando de control `0xBB 0x01 <duración>` al ESP32-S3 por USB o BLE
- Duración ajustable desde el script: 10 ms – 500 ms
- Activa GPIO 12 (VALVE_OUT) durante la duración configurada y retorna al estado anterior
- Útil para pruebas de actuación sin ciclo de disparo

### C.4 Ventana flotante — Simulador intercambiable

```
┌────────────────────────────────────────┐
│  SIMULADOR  [Intercambiar con Real ⇄]  │
├────────────────────────────────────────┤
│  S1 [toggle]  S2 [toggle]  S3 [toggle] │
│                                        │
│  ENC_H: ─────●─────── +150            │
│  ENC_V: ─────●─────── -30             │
│                                        │
│  Balas Max: [50]  Actuales: [32]       │
│  Cadencia disparo: [██░░] 300 rpm      │
│                                        │
│  [▶ Simular ráfaga]  [⟳ Recargar]     │
└────────────────────────────────────────┘
```

El modo **"Intercambiar con Real ⇄"** conecta los datos del simulador a las mismas vistas del dashboard, permitiendo validar la interfaz completa sin el microcontrolador físico conectado. El simulador replica la máquina de estados real del firmware (S1/S2/S3 + conteo de balas + encoders).

### C.5 Flujo de conexión automática del script

```
Script inicia
    │
    ├─► Escanea puertos COM/ttyUSB buscando ESP32-S3
    │       Si encuentra → envía handshake (0xAA 0x55)
    │       Si confirma  → modo USB activo → estado "🔵 USB"
    │
    └─► Si no hay USB → escanea dispositivos BLE "M2-DAQ"
            Si encuentra → conecta → modo BLE → estado "🟡 BLE"
            Si no        → estado "🔴 Desconectado"
                           → ofrece activar modo Simulador
```

---

## Fases de Implementación

| Fase | Módulo | Entregable | Depende de |
|---|---|---|---|
| **1** | A — Firmware S3 | `config.py`, `sensors.py` (sin IMU), `hid_mouse.py`, `hid_kbd.py` | — |
| **2** | A — Firmware S3 | `transport.py` (USB + BLE + handshake) + LED RGB en `main.py` | Fase 1 |
| **3** | A — Firmware S3 | `espnow_tx.py` + integración completa en `main.py` | Fase 1 |
| **4** | B — Firmware C3 | `gc9a01.py` driver SPI desde cero | — |
| **5** | B — Firmware C3 | `display.py` animación balística + `main.py` ESPNow RX | Fase 4 |
| **6** | C — Script Python | `protocol.py` + `usb_handler.py` + `ble_handler.py` | Fase 2 |
| **7** | C — Script Python | Dashboard PySide6 + gráficas pyqtgraph + botón válvula | Fase 6 |
| **8** | C — Script Python | Ventana flotante simulador intercambiable | Fase 7 |

---

## Resumen de archivos del proyecto optimizado

| Módulo | Archivos | Líneas estimadas |
|---|---|---|
| Firmware ESP32-S3 | 9 archivos `.py` | ~700 |
| Firmware ESP32-C3 | 5 archivos `.py` | ~400 |
| Script Python | 10 archivos `.py` | ~1200 |
| **Total** | **24 archivos** | **~2300** |

**Reducción vs proyecto de referencia:** se elimina servidor HTTP/WebSocket, WiFi stack, IMU/giroscopio, toda la capa web (HTML/JS/CSS) y el servidor de archivos estáticos. El HID y la lógica de sensores/actuadores se conservan y optimizan.
