#!/usr/bin/env python3
import threading
import time
from collections import deque
from dataclasses import asdict, dataclass
from enum import Enum
from typing import Callable, Optional

from controller.fan import FanController
from controller.ssr import SSRController
from controller.temperature import TemperatureController
from profiles.profile_loader import RoastProfile
from utils.logging import RoastLogger


class RoastState(str, Enum):
    IDLE = "IDLE"
    PREHEATING = "PREHEATING"
    READY_FOR_BEAN_DROP = "READY_FOR_BEAN_DROP"
    ROASTING = "ROASTING"
    STOPPING = "STOPPING"
    FAULT = "FAULT"


@dataclass
class CommandResult:
    ok: bool
    message: str


@dataclass
class RoastSnapshot:
    state: str = RoastState.IDLE.value
    elapsed_s: float = 0.0
    target_temp_c: float = 0.0
    actual_temp_c: float = 0.0
    ror_c_per_min: Optional[float] = None
    stage_label: str = "Idle"
    stage_elapsed_s: float = 0.0
    heater_on_time_s: float = 0.0
    profile_name: str = ""
    fault_message: Optional[str] = None
    last_event_marker: Optional[str] = None
    last_event_elapsed_s: Optional[float] = None
    ts_epoch: float = 0.0


STAGE_EVENT_LABELS = {
    "dry_end": "Dry End",
    "maillard": "Maillard",
    "first_crack_start": "First Crack Start",
    "first_crack_end": "First Crack End",
    "second_crack_start": "Second Crack Start",
    "second_crack_end": "Second Crack End",
    "drop": "Drop",
}

ROR_DISPLAY_WARMUP_S = 30.0


class RoastEngine:
    def __init__(self, ssr_pin=26, log_file="roast_log.csv"):
        self.ssr_pin = ssr_pin
        self.log_file = log_file

        self._lock = threading.RLock()
        self._thread: Optional[threading.Thread] = None
        self._stop_event = threading.Event()
        self._subscribers: list[Callable[[dict], None]] = []

        self.profile: Optional[RoastProfile] = None
        self.ssr: Optional[SSRController] = None
        self.temp_controller: Optional[TemperatureController] = None
        self.fan: Optional[FanController] = None
        self.logger: Optional[RoastLogger] = None

        self.state = RoastState.IDLE
        self.temp_offset = 0.0
        self.manual_fan_speed: Optional[int] = None
        self.session_start_time: Optional[float] = None
        self.roast_start_time: Optional[float] = None
        self.stage_label = "Idle"
        self.stage_start_time: Optional[float] = None
        self.fault_message: Optional[str] = None

        self._target_temp_c = 0.0
        self._actual_temp_c = 0.0
        self._heater_on_time_s = 0.0
        self._ror_c_per_min: Optional[float] = None
        self._pending_event_marker: Optional[str] = None
        self._last_event_marker: Optional[str] = None
        self._last_event_elapsed_s: Optional[float] = None
        self._did_reduce_preheat_fan = False
        self._is_cleaned_up = True
        self._last_elapsed_s = 0.0
        self._last_stage_elapsed_s = 0.0

        self._ror_samples: deque[tuple[float, float]] = deque()
        self._last_ror_sample_ts = 0.0
        self._emergency_stop = False

    def subscribe(self, callback: Callable[[dict], None]) -> None:
        with self._lock:
            self._subscribers.append(callback)

    def get_snapshot(self) -> RoastSnapshot:
        with self._lock:
            now = time.time()
            elapsed = self._compute_elapsed(now)
            stage_elapsed = self._compute_stage_elapsed(now)
            return RoastSnapshot(
                state=self.state.value,
                elapsed_s=elapsed,
                target_temp_c=self._target_temp_c,
                actual_temp_c=self._actual_temp_c,
                ror_c_per_min=self._ror_c_per_min,
                stage_label=self.stage_label,
                stage_elapsed_s=stage_elapsed,
                heater_on_time_s=self._heater_on_time_s,
                profile_name=self.profile.name if self.profile else "",
                fault_message=self.fault_message,
                last_event_marker=self._last_event_marker,
                last_event_elapsed_s=self._last_event_elapsed_s,
                ts_epoch=now,
            )

    def start(self, profile_file: str) -> CommandResult:
        with self._lock:
            if self.state not in (RoastState.IDLE, RoastState.FAULT):
                return CommandResult(False, f"Cannot start from state {self.state.value}")

            self._initialize_run(profile_file)
            self._stop_event.clear()
            self._thread = threading.Thread(target=self._run_loop, daemon=True)
            self._thread.start()
            return CommandResult(True, "Roast session started")

    def bean_drop(self) -> CommandResult:
        with self._lock:
            if self.state not in (RoastState.READY_FOR_BEAN_DROP, RoastState.PREHEATING):
                return CommandResult(False, f"Bean drop not allowed in state {self.state.value}")
            now = time.time()
            self.roast_start_time = now
            self.stage_label = "Drying"
            self.stage_start_time = now
            self.state = RoastState.ROASTING
            self._ror_c_per_min = None
            self._pending_event_marker = "bean_drop"
            self._last_event_marker = "bean_drop"
            self._last_event_elapsed_s = self._compute_elapsed(now)
            if self.fan:
                self.fan.set_speed(100)
            return CommandResult(True, "Bean drop accepted, roast started")

    def mark_stage(self, stage: str) -> CommandResult:
        with self._lock:
            if self.state != RoastState.ROASTING:
                return CommandResult(False, f"Stage marking not allowed in state {self.state.value}")
            if stage not in STAGE_EVENT_LABELS:
                return CommandResult(False, f"Unknown stage marker: {stage}")
            now = time.time()
            self.stage_label = STAGE_EVENT_LABELS[stage]
            self.stage_start_time = now
            self._pending_event_marker = stage
            self._last_event_marker = stage
            self._last_event_elapsed_s = self._compute_elapsed(now)
            return CommandResult(True, f"Stage marked: {self.stage_label}")

    def set_fan(self, percent: int) -> CommandResult:
        with self._lock:
            if self.state in (RoastState.IDLE, RoastState.STOPPING):
                return CommandResult(False, f"Fan command not allowed in state {self.state.value}")
            if percent < 0 or percent > 100:
                return CommandResult(False, "Fan percent must be in range 0..100")
            self.manual_fan_speed = percent
            if self.fan:
                self.fan.set_speed(percent)
            return CommandResult(True, f"Fan set to {percent}%")

    def set_temp_offset(self, delta_c: float) -> CommandResult:
        with self._lock:
            if self.state in (RoastState.IDLE, RoastState.STOPPING):
                return CommandResult(False, f"Temp offset not allowed in state {self.state.value}")
            self.temp_offset += delta_c
            return CommandResult(True, f"Temp offset: {self.temp_offset:+.1f}C")

    def stop(self) -> CommandResult:
        thread_to_join = None
        with self._lock:
            if self.state == RoastState.IDLE:
                return CommandResult(True, "Already stopped")
            self.state = RoastState.STOPPING
            self._stop_event.set()
            thread_to_join = self._thread

        if thread_to_join and thread_to_join.is_alive() and thread_to_join is not threading.current_thread():
            thread_to_join.join(timeout=5)

        with self._lock:
            if self.state != RoastState.FAULT:
                self.state = RoastState.IDLE
            self._publish_snapshot_unlocked()
        return CommandResult(True, "Stop requested")

    def emergency_shutdown(self) -> CommandResult:
        """Immediate, fail-safe shutdown that bypasses normal flow."""
        thread_to_join = None
        with self._lock:
            self._emergency_stop = True
            self._stop_event.set()
            self.state = RoastState.FAULT
            self.fault_message = "Emergency shutdown activated"
            thread_to_join = self._thread
            self._publish_snapshot_unlocked()

        # Force hardware off in caller thread immediately.
        self._force_hardware_off()

        if thread_to_join and thread_to_join.is_alive() and thread_to_join is not threading.current_thread():
            thread_to_join.join(timeout=1)

        with self._lock:
            self.state = RoastState.IDLE
            self._publish_snapshot_unlocked()
        return CommandResult(True, "Emergency shutdown complete")

    def _initialize_run(self, profile_file: str) -> None:
        self.profile = RoastProfile(profile_file)
        self.ssr = SSRController(self.ssr_pin, self.profile.pwm_period)
        self.temp_controller = TemperatureController(
            pwm_period=self.profile.pwm_period,
            pid_gains=self.profile.pid_gains,
        )
        self.fan = FanController()
        self.logger = RoastLogger(self.log_file, self.profile.name)

        now = time.time()
        self.session_start_time = now
        self.roast_start_time = None
        self.stage_label = "Preheating" if self.profile.preheat else "Drying"
        self.stage_start_time = now
        self.temp_offset = 0.0
        self.manual_fan_speed = None
        self.fault_message = None
        self._target_temp_c = 0.0
        self._actual_temp_c = 0.0
        self._heater_on_time_s = 0.0
        self._ror_c_per_min = None
        self._pending_event_marker = None
        self._last_event_marker = None
        self._last_event_elapsed_s = None
        self._did_reduce_preheat_fan = False
        self._is_cleaned_up = False
        self._last_elapsed_s = 0.0
        self._last_stage_elapsed_s = 0.0

        self._ror_samples.clear()
        self._last_ror_sample_ts = 0.0
        self._emergency_stop = False

        if self.profile.preheat:
            self.state = RoastState.PREHEATING
            preheat_temp = float(self.profile.preheat["temp_c"])
            self.temp_controller.set_target(preheat_temp)
            self._target_temp_c = preheat_temp
            self.fan.set_speed(100)
        else:
            self.state = RoastState.ROASTING
            self.roast_start_time = now
            self.fan.set_speed(100)
            self._pending_event_marker = "bean_drop"
            self._last_event_marker = "bean_drop"
            self._last_event_elapsed_s = self._compute_elapsed(now)

        self._publish_snapshot_unlocked()

    def _run_loop(self) -> None:
        try:
            while not self._stop_event.is_set():
                with self._lock:
                    state = self.state

                if state == RoastState.PREHEATING:
                    self._preheat_step()
                elif state == RoastState.READY_FOR_BEAN_DROP:
                    self._hold_preheat_step()
                elif state == RoastState.ROASTING:
                    self._roast_step()
                elif state in (RoastState.STOPPING, RoastState.IDLE, RoastState.FAULT):
                    break
                else:
                    time.sleep(0.1)
        except Exception as exc:
            with self._lock:
                self.state = RoastState.FAULT
                self.fault_message = str(exc)
                self._publish_snapshot_unlocked()
            print(f"[ERROR] RoastEngine fault: {exc}")
        finally:
            self._cleanup()
            with self._lock:
                if self.state not in (RoastState.FAULT, RoastState.IDLE):
                    self.state = RoastState.IDLE
                self._publish_snapshot_unlocked()

    def _preheat_step(self) -> None:
        with self._lock:
            if not self.temp_controller or not self.profile:
                return
            target = float(self.profile.preheat["temp_c"])
            self.temp_controller.set_target(target)
            self._target_temp_c = target

        current_temp = self.temp_controller.read_temperature()
        now = time.time()
        # RoR is not meaningful before bean drop.
        ror = None
        on_time = self.temp_controller.calculate_output(current_temp)

        with self._lock:
            self._actual_temp_c = current_temp
            self._heater_on_time_s = on_time
            self._ror_c_per_min = ror
            elapsed = self._compute_elapsed(now)
            marker = self._consume_pending_event_marker_unlocked()
            if self.logger:
                self.logger.log_step(
                    elapsed,
                    "Preheating",
                    elapsed,
                    self._target_temp_c,
                    current_temp,
                    on_time,
                    ror_c_per_min=ror,
                    event_marker=marker,
                )
            if self.fan and current_temp >= self._target_temp_c - 2.0 and not self._did_reduce_preheat_fan:
                self.fan.set_speed(20)
                self._did_reduce_preheat_fan = True
                self.state = RoastState.READY_FOR_BEAN_DROP
                self.stage_label = "Preheat Complete"
                self.stage_start_time = now
            self._publish_snapshot_unlocked()

        if self._emergency_stop:
            return
        if self.ssr:
            self.ssr.control_output(on_time)

    def _hold_preheat_step(self) -> None:
        with self._lock:
            if not self.temp_controller:
                return
            target = self._target_temp_c
            self.temp_controller.set_target(target)

        current_temp = self.temp_controller.read_temperature()
        now = time.time()
        # RoR is not meaningful before bean drop.
        ror = None
        on_time = self.temp_controller.calculate_output(current_temp)

        with self._lock:
            self._actual_temp_c = current_temp
            self._heater_on_time_s = on_time
            self._ror_c_per_min = ror
            elapsed = self._compute_elapsed(now)
            marker = self._consume_pending_event_marker_unlocked()
            if self.logger:
                self.logger.log_step(
                    elapsed,
                    "Preheat Complete",
                    self._compute_stage_elapsed(now),
                    target,
                    current_temp,
                    on_time,
                    ror_c_per_min=ror,
                    event_marker=marker,
                )
            self._publish_snapshot_unlocked()

        if self._emergency_stop:
            return
        if self.ssr:
            self.ssr.control_output(on_time)

    def _roast_step(self) -> None:
        with self._lock:
            if not self.profile or not self.temp_controller:
                return
            now = time.time()
            roast_elapsed = now - self.roast_start_time if self.roast_start_time else 0.0
            base_target = self.profile.interpolate_setpoint(roast_elapsed)
            target = base_target + self.temp_offset
            self.temp_controller.set_target(target)
            self._target_temp_c = target

        current_temp = self.temp_controller.read_temperature()
        now = time.time()
        ror = self._compute_ror(now, current_temp)
        on_time = self.temp_controller.calculate_output(current_temp)

        with self._lock:
            roast_elapsed = now - self.roast_start_time if self.roast_start_time else 0.0
            stage_elapsed = self._compute_stage_elapsed(now)
            self._actual_temp_c = current_temp
            self._heater_on_time_s = on_time
            # Hide RoR on UI/chart during early post-drop transient.
            self._ror_c_per_min = None if roast_elapsed < ROR_DISPLAY_WARMUP_S else ror
            marker = self._consume_pending_event_marker_unlocked()
            if self.logger:
                self.logger.log_step(
                    roast_elapsed,
                    self.stage_label,
                    stage_elapsed,
                    self._target_temp_c,
                    current_temp,
                    on_time,
                    # Keep logging real RoR even while UI RoR is temporarily hidden.
                    ror_c_per_min=ror,
                    event_marker=marker,
                )
            self._publish_snapshot_unlocked()

        if self._emergency_stop:
            return
        if self.ssr:
            self.ssr.control_output(on_time)

    def _compute_ror(self, now: float, current_temp: float) -> Optional[float]:
        with self._lock:
            if self._last_ror_sample_ts == 0.0 or (now - self._last_ror_sample_ts) >= 3.0:
                self._ror_samples.append((now, current_temp))
                self._last_ror_sample_ts = now

            min_keep = now - 40.0
            while self._ror_samples and self._ror_samples[0][0] < min_keep:
                self._ror_samples.popleft()

            points = [p for p in self._ror_samples if p[0] >= (now - 30.0)]
            if len(points) < 2:
                return None

            x0 = points[0][0]
            xs = [p[0] - x0 for p in points]
            ys = [p[1] for p in points]
            x_mean = sum(xs) / len(xs)
            y_mean = sum(ys) / len(ys)

            num = sum((x - x_mean) * (y - y_mean) for x, y in zip(xs, ys))
            den = sum((x - x_mean) ** 2 for x in xs)
            if den == 0:
                return None

            slope_c_per_s = num / den
            return slope_c_per_s * 60.0

    def _compute_elapsed(self, now: float) -> float:
        if self.state in (RoastState.PREHEATING, RoastState.READY_FOR_BEAN_DROP, RoastState.ROASTING):
            if not self.session_start_time:
                self._last_elapsed_s = 0.0
            else:
                self._last_elapsed_s = max(0.0, now - self.session_start_time)
        return self._last_elapsed_s

    def _compute_stage_elapsed(self, now: float) -> float:
        if self.state in (RoastState.PREHEATING, RoastState.READY_FOR_BEAN_DROP, RoastState.ROASTING):
            if not self.stage_start_time:
                self._last_stage_elapsed_s = 0.0
            else:
                self._last_stage_elapsed_s = max(0.0, now - self.stage_start_time)
        return self._last_stage_elapsed_s

    def _consume_pending_event_marker_unlocked(self) -> Optional[str]:
        marker = self._pending_event_marker
        self._pending_event_marker = None
        return marker

    def _publish_snapshot_unlocked(self) -> None:
        snapshot = asdict(self.get_snapshot())
        for callback in list(self._subscribers):
            try:
                callback(snapshot)
            except Exception:
                continue

    def _cleanup(self) -> None:
        with self._lock:
            if self._is_cleaned_up:
                return
            self._is_cleaned_up = True

        self._force_hardware_off()

    def _force_hardware_off(self) -> None:
        try:
            if self.ssr:
                self.ssr.turn_off()
        except Exception:
            pass

        try:
            if self.ssr:
                self.ssr.cleanup()
        except Exception:
            pass

        try:
            if self.fan:
                self.fan.shutdown()
        except Exception:
            pass

        try:
            if self.logger:
                self.logger.close()
        except Exception:
            pass

    def shutdown(self) -> None:
        self.stop()
