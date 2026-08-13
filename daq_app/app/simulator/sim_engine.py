# sim_engine.py — Máquina de estados real del firmware (S1/S2/S3 + encoders).
# Genera frames idénticos a los del ESP32-S3 a 50 Hz, incluyendo el conteo
# de balas y el bloqueo de válvula por fin de munición.

import time

from PySide6.QtCore import QObject, QTimer, Signal

from ..connection.protocol import Frame


class MouseEventData:
    """Evento de movimiento del mouse: delta en encoders."""
    def __init__(self, dx: int, dy: int):
        self.dx = dx
        self.dy = dy

PERIOD_MS = 20        # 50 Hz
RELOAD_HOLD_S = 2.5   # S1 debe sostenerse este tiempo para recargar (igual que firmware)


class SimEngine(QObject):
    frame_ready = Signal(Frame)
    mouse_moved = Signal(MouseEventData)   # delta encoder → movimiento mouse
    fire_click = Signal()                  # flanco S3 → clic HID

    def __init__(self, parent=None):
        super().__init__(parent)
        # Entradas controlables (sim_controls)
        self.s1 = False
        self.s2 = False
        self.s3 = False
        self.enc_h = 0
        self.enc_v = 0
        self._enc_h_prev = 0
        self._enc_v_prev = 0
        self.magazine_max = 50
        self.rate_rpm = 300

        # Estado interno (réplica del firmware)
        self._rounds_fired = 0
        self._valve_blocked = False
        self._s1_prev = False
        self._s3_prev = False
        self._s1_hold_start = 0.0
        self._s1_reloaded_this_hold = False

        # Ráfaga automática
        self._burst_active = False
        self._burst_phase_ms = 0

        # Pulso manual (independiente del toggle S3): mismo efecto que un
        # disparo real — cuenta bala, activa válvula/HID-graph y bloquea
        # si agota el cargador.
        self._manual_pulse_until = 0.0

        self._t0 = time.monotonic()
        self._timer = QTimer(self)
        self._timer.setInterval(PERIOD_MS)
        self._timer.timeout.connect(self._tick)

    # ── Control externo ─────────────────────────────────────────────────
    def start(self):
        self._timer.start()

    def stop(self):
        self._timer.stop()

    def set_current_rounds(self, current: int):
        """Fija balas actuales (balas restantes) directamente."""
        current = max(0, min(self.magazine_max, current))
        self._rounds_fired = self.magazine_max - current
        self._valve_blocked = self._rounds_fired >= self.magazine_max

    def start_burst(self):
        self._burst_active = True
        self._burst_phase_ms = 0

    def stop_burst(self):
        self._burst_active = False
        self.s3 = False

    def reload(self):
        """Recarga instantánea desde los controles del simulador (botón)."""
        self._rounds_fired = 0
        self._valve_blocked = False
        self._s1_prev = False
        self._s1_reloaded_this_hold = False

    def manual_pulse(self, duration_ms=50):
        """Pulso manual de válvula: actúa igual que un disparo real —
        cuenta la bala, bloquea si agota el cargador y mantiene la
        válvula/gráfica activas por duration_ms."""
        if self._valve_blocked:
            return
        self._rounds_fired += 1
        if self._rounds_fired >= self.magazine_max:
            self._valve_blocked = True
            return
        self._manual_pulse_until = time.monotonic() + duration_ms / 1000.0

    @property
    def rounds_left(self) -> int:
        return max(0, self.magazine_max - self._rounds_fired)

    @property
    def valve_blocked(self) -> bool:
        return self._valve_blocked

    # ── Tick 50 Hz ──────────────────────────────────────────────────────
    def _check_encoder_delta(self):
        """Detecta cambios en los encoders y emite evento de mouse."""
        dx = self.enc_h - self._enc_h_prev
        dy = self.enc_v - self._enc_v_prev
        if dx != 0 or dy != 0:
            self.mouse_moved.emit(MouseEventData(dx, dy))
            self._enc_h_prev = self.enc_h
            self._enc_v_prev = self.enc_v

    def _tick(self):
        s1, s2, s3 = self.s1, self.s2, self.s3

        # Ráfaga: pulso S3 según cadencia (rpm)
        if self._burst_active and self.rate_rpm > 0:
            cycle_ms = 60000 // self.rate_rpm
            self._burst_phase_ms = (self._burst_phase_ms + PERIOD_MS) % cycle_ms
            s3 = self._burst_phase_ms < min(60, cycle_ms // 2)
            if self._valve_blocked:
                self._burst_active = False
                s3 = False

        # Máquina de estados de la válvula (idéntica al firmware)
        s1_rising = s1 and not self._s1_prev
        s1_falling = (not s1) and self._s1_prev
        self._s1_prev = s1
        s3_rising = s3 and not self._s3_prev
        self._s3_prev = s3

        now = time.monotonic()
        if s1_rising:
            self._s1_hold_start = now
            self._s1_reloaded_this_hold = False
        if s1_falling:
            self._s1_reloaded_this_hold = False

        # Recarga por sostenimiento de S1 (en cualquier momento, no solo bloqueada)
        if s1 and not self._s1_reloaded_this_hold:
            if now - self._s1_hold_start >= RELOAD_HOLD_S:
                self._rounds_fired = 0
                self._valve_blocked = False
                self._s1_reloaded_this_hold = True

        fire_allowed = not self._valve_blocked
        if fire_allowed and s3_rising:
            self._rounds_fired += 1
            if self._rounds_fired >= self.magazine_max:
                self._valve_blocked = True

        # Pulso manual: activo mientras dure, con el mismo efecto visual
        # que un disparo real (s3/valve encendidos) sin afectar el flanco de S3.
        manual_active = now < self._manual_pulse_until
        # Cargador agotado: ni la válvula ni el "disparo" visible deben
        # activarse hasta que se recargue (aunque S3 siga presionado).
        shot_visual = (s3 or manual_active) and not self._valve_blocked

        # Eventos de mouse y disparo para ControlLink (cuando estén activados)
        if fire_allowed and s3_rising:
            self.fire_click.emit()
        self._check_encoder_delta()

        frame = Frame(
            ts_ms=int((now - self._t0) * 1000),
            s1=s1, s2=s2, s3=shot_visual,
            valve_blocked=self._valve_blocked,
            valve=shot_visual and not self._valve_blocked,
            enc_h=self.enc_h,
            enc_v=self.enc_v,
            rounds_fired=self._rounds_fired,
            magazine_max=self.magazine_max,
        )
        self.frame_ready.emit(frame)
