#!/usr/bin/env python3
import time
import unittest
from unittest.mock import patch

from engine.roast_engine import RoastEngine, RoastState


class FakeProfile:
    def __init__(self, profile_file=None):
        self.name = "Fake"
        self.description = "fake"
        self.pid_gains = (2.0, 0.2, 2.0)
        self.pwm_period = 0.01
        self.profile_data = [(0.0, 150.0), (60.0, 180.0)]
        self.preheat = {"temp_c": 180} if "with_preheat" in (profile_file or "") else None

    def interpolate_setpoint(self, elapsed):
        return 150.0 + min(elapsed, 60.0) * 0.5


class FakeSSR:
    def __init__(self, *args, **kwargs):
        self.off = False

    def control_output(self, on_time):
        time.sleep(0.005)

    def turn_off(self):
        self.off = True

    def cleanup(self):
        self.off = True


class FakeTemp:
    def __init__(self, *args, **kwargs):
        self.setpoint = kwargs.get("initial_setpoint", 60.0)
        self.current = 200.0

    def read_temperature(self):
        return self.current

    def set_target(self, target_temp):
        self.setpoint = target_temp

    def calculate_output(self, current_temp):
        return 0.0


class FakeFan:
    def __init__(self, *args, **kwargs):
        self.last_speed = None

    def set_speed(self, percentage):
        self.last_speed = percentage

    def shutdown(self):
        pass


class FakeLogger:
    def __init__(self, *args, **kwargs):
        self.rows = []

    def log_step(self, *args, **kwargs):
        self.rows.append((args, kwargs))

    def close(self):
        pass


class RoastEngineTests(unittest.TestCase):
    def setUp(self):
        self.patches = [
            patch("engine.roast_engine.RoastProfile", FakeProfile),
            patch("engine.roast_engine.SSRController", FakeSSR),
            patch("engine.roast_engine.TemperatureController", FakeTemp),
            patch("engine.roast_engine.FanController", FakeFan),
            patch("engine.roast_engine.RoastLogger", FakeLogger),
        ]
        for p in self.patches:
            p.start()

    def tearDown(self):
        for p in reversed(self.patches):
            p.stop()

    def wait_for_state(self, engine, expected, timeout=1.5):
        deadline = time.time() + timeout
        while time.time() < deadline:
            if engine.get_snapshot().state == expected:
                return True
            time.sleep(0.01)
        return False

    def test_state_transitions_preheat_to_roast_to_idle(self):
        engine = RoastEngine(log_file="test.csv")
        result = engine.start("with_preheat.json")
        self.assertTrue(result.ok)
        self.assertTrue(self.wait_for_state(engine, RoastState.READY_FOR_BEAN_DROP.value))

        drop = engine.bean_drop()
        self.assertTrue(drop.ok)
        self.assertTrue(self.wait_for_state(engine, RoastState.ROASTING.value))

        stop = engine.stop()
        self.assertTrue(stop.ok)
        self.assertTrue(self.wait_for_state(engine, RoastState.IDLE.value))

    def test_invalid_command_in_idle(self):
        engine = RoastEngine(log_file="test.csv")
        result = engine.mark_stage("dry_end")
        self.assertFalse(result.ok)
        self.assertIn("not allowed", result.message)

    def test_extended_stage_markers_are_accepted(self):
        engine = RoastEngine(log_file="test.csv")
        result = engine.start("no_preheat.json")
        self.assertTrue(result.ok)
        self.assertTrue(self.wait_for_state(engine, RoastState.ROASTING.value))

        for stage in (
            "dry_end",
            "maillard",
            "first_crack_start",
            "first_crack_end",
            "second_crack_start",
            "second_crack_end",
            "drop",
        ):
            marked = engine.mark_stage(stage)
            self.assertTrue(marked.ok, msg=f"Stage should be accepted: {stage}")
        engine.stop()

    def test_ror_calculation_linear(self):
        engine = RoastEngine(log_file="test.csv")
        base = 1000.0
        for i in range(11):
            now = base + i * 3.0
            temp = 100.0 + i * 0.5
            ror = engine._compute_ror(now, temp)
        self.assertIsNotNone(ror)
        self.assertAlmostEqual(ror, 10.0, delta=0.8)

    def test_stage_timing_resets_on_mark(self):
        engine = RoastEngine(log_file="test.csv")
        result = engine.start("no_preheat.json")
        self.assertTrue(result.ok)
        self.assertTrue(self.wait_for_state(engine, RoastState.ROASTING.value))

        time.sleep(0.05)
        before = engine.get_snapshot().stage_elapsed_s
        mark = engine.mark_stage("first_crack_start")
        self.assertTrue(mark.ok)
        time.sleep(0.01)
        after = engine.get_snapshot().stage_elapsed_s

        self.assertGreater(before, 0.0)
        self.assertLess(after, before)
        engine.stop()

    def test_emergency_shutdown_forces_idle_and_off(self):
        engine = RoastEngine(log_file="test.csv")
        result = engine.start("no_preheat.json")
        self.assertTrue(result.ok)
        self.assertTrue(self.wait_for_state(engine, RoastState.ROASTING.value))

        emergency = engine.emergency_shutdown()
        self.assertTrue(emergency.ok)
        self.assertEqual(engine.get_snapshot().state, RoastState.IDLE.value)
        self.assertTrue(engine.ssr.off)


if __name__ == "__main__":
    unittest.main()
