#!/usr/bin/env python3
import time
import RPi.GPIO as GPIO

class SSRController:
    def __init__(self, ssr_pin=26, pwm_period=0.5):
        self.ssr_pin = ssr_pin
        self.pwm_period = pwm_period
        
        # GPIO setup
        GPIO.setmode(GPIO.BCM)
        GPIO.setup(self.ssr_pin, GPIO.OUT)
        GPIO.output(self.ssr_pin, GPIO.LOW)

    def _set_output_verified(self, expected_state, retries=3, delay_s=0.01, verbose=False):
        """Set GPIO output and verify readback reaches expected state."""
        for _ in range(retries):
            GPIO.output(self.ssr_pin, expected_state)
            if GPIO.input(self.ssr_pin) == expected_state:
                if verbose:
                    state_name = "HIGH" if expected_state == GPIO.HIGH else "LOW"
                    print(f"[INFO] SSR GPIO {self.ssr_pin} verified {state_name}")
                return
            time.sleep(delay_s)
        state_name = "HIGH" if expected_state == GPIO.HIGH else "LOW"
        raise RuntimeError(f"SSR GPIO {self.ssr_pin} failed to reach {state_name}")
    
    def control_output(self, on_time):
        """Control SSR with PWM-like behavior"""
        try:
            if on_time > 0:
                self._set_output_verified(GPIO.HIGH)
                time.sleep(on_time)
            if on_time < self.pwm_period:
                self._set_output_verified(GPIO.LOW)
                time.sleep(self.pwm_period - on_time)
        except Exception as e:
            print(f"[ERROR] SSR/GPIO control failed: {e}")
            raise
    
    def turn_off(self):
        """Turn off SSR"""
        self._set_output_verified(GPIO.LOW, verbose=True)
    
    def cleanup(self):
        """Clean up GPIO"""
        self._set_output_verified(GPIO.LOW, verbose=True)
        GPIO.cleanup()
