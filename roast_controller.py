#!/usr/bin/env python3
import select
import sys
import termios
import threading
import time
import tty

from engine.roast_engine import RoastEngine, RoastState


class RoastController:
    def __init__(self, ssr_pin=26, roast_profile_file=None, log_file="roast_log.csv"):
        self.roast_profile_file = roast_profile_file
        self.engine = RoastEngine(ssr_pin=ssr_pin, log_file=log_file)
        self.running = False
        self.manual_fan_speed = None
        self.temp_offset = 0.0
        self._cli_stage_order = ["dry_end", "first_crack_start", "first_crack_end", "drop"]
        self._cli_stage_index = 0

    def start(self):
        """Start roast control and block until session ends."""
        if not self.roast_profile_file:
            raise ValueError("roast_profile_file is required")

        result = self.engine.start(self.roast_profile_file)
        if not result.ok:
            raise RuntimeError(result.message)

        snapshot = self.engine.get_snapshot()
        print(f"[INFO] Roast session started for '{snapshot.profile_name}'")
        if snapshot.state == RoastState.PREHEATING.value:
            print("[INFO] Preheating started. Press ENTER when beans are dropped.")
        else:
            print("[INFO] Starting roast phase")
        print("[INFO] Controls: 1-9=Fan%, 0=100%, +/-=Temp±5°C, ENTER=Bean Drop/Stage, r=Reset, q=Quit")

        self.running = True
        self._cli_stage_index = 0
        keyboard_thread = threading.Thread(target=self.keyboard_loop, daemon=True)
        keyboard_thread.start()

        try:
            while self.running:
                state = self.engine.get_snapshot().state
                if state in (RoastState.IDLE.value, RoastState.FAULT.value):
                    break
                time.sleep(0.2)
        finally:
            self.running = False

    def keyboard_loop(self):
        """Handle keyboard controls during roast."""
        if not sys.stdin.isatty():
            return

        old_settings = termios.tcgetattr(sys.stdin)
        try:
            tty.setraw(sys.stdin.fileno())
            while self.running:
                if select.select([sys.stdin], [], [], 0.1)[0]:
                    key = sys.stdin.read(1)
                    if ord(key) == 3:  # Ctrl+C
                        self.shutdown()
                        break
                    if ord(key) == 13:  # ENTER
                        state = self.engine.get_snapshot().state
                        if state in (RoastState.PREHEATING.value, RoastState.READY_FOR_BEAN_DROP.value):
                            result = self.engine.bean_drop()
                            if result.ok:
                                print("\n[INFO] Beans dropped! Starting roast profile...")
                            else:
                                print(f"\n[WARN] {result.message}")
                        elif state == RoastState.ROASTING.value:
                            if self._cli_stage_index < len(self._cli_stage_order):
                                stage_key = self._cli_stage_order[self._cli_stage_index]
                                result = self.engine.mark_stage(stage_key)
                                if result.ok:
                                    self._cli_stage_index += 1
                                    print(f"\n[STAGE] {result.message}")
                                else:
                                    print(f"\n[WARN] {result.message}")
                            else:
                                print("\n[INFO] Final stage already marked.")
                        continue
                    self.handle_keypress(key)
        except Exception:
            pass
        finally:
            termios.tcsetattr(sys.stdin, termios.TCSADRAIN, old_settings)

    def handle_keypress(self, key):
        """Process keyboard input for realtime adjustments."""
        if key in "123456789":
            fan_speed = int(key) * 10
            result = self.engine.set_fan(fan_speed)
            if result.ok:
                self.manual_fan_speed = fan_speed
                print(f"[MANUAL] Fan speed: {fan_speed}%")
        elif key == "0":
            result = self.engine.set_fan(100)
            if result.ok:
                self.manual_fan_speed = 100
                print("[MANUAL] Fan speed: 100%")
        elif key == "+":
            result = self.engine.set_temp_offset(5.0)
            if result.ok:
                self.temp_offset += 5.0
                print(f"[MANUAL] Temp offset: {self.temp_offset:+.1f}°C")
        elif key == "-":
            result = self.engine.set_temp_offset(-5.0)
            if result.ok:
                self.temp_offset -= 5.0
                print(f"[MANUAL] Temp offset: {self.temp_offset:+.1f}°C")
        elif key == "r":
            if self.temp_offset != 0.0:
                self.engine.set_temp_offset(-self.temp_offset)
            self.temp_offset = 0.0
            self.manual_fan_speed = None
            self.engine.set_fan(100)
            print("[MANUAL] Reset - Fan: 100%, Temp offset: 0°C")
        elif key == "q":
            print("[MANUAL] Quit requested")
            self.shutdown()

    def shutdown(self):
        """Shutdown the controller safely."""
        if not self.running and self.engine.get_snapshot().state == RoastState.IDLE.value:
            return

        print("[INFO] Shutting down controller...")
        self.running = False
        self.engine.shutdown()
        print("[INFO] System shut down safely. SSR OFF. Log saved.")
