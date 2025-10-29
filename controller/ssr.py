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
    
    def control_output(self, on_time):
        """Control SSR with PWM-like behavior"""
        try:
            if on_time > 0:
                GPIO.output(self.ssr_pin, GPIO.HIGH)
                time.sleep(on_time)
            if on_time < self.pwm_period:
                GPIO.output(self.ssr_pin, GPIO.LOW)
                time.sleep(self.pwm_period - on_time)
        except Exception as e:
            print(f"[ERROR] SSR/GPIO control failed: {e}")
            raise
    
    def turn_off(self):
        """Turn off SSR"""
        GPIO.output(self.ssr_pin, GPIO.LOW)
    
    def cleanup(self):
        """Clean up GPIO"""
        GPIO.output(self.ssr_pin, GPIO.LOW)
        GPIO.cleanup()