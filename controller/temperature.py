#!/usr/bin/env python3
from simple_pid import PID

class TemperatureController:
    def __init__(
        self,
        temp_raw_path="/sys/bus/iio/devices/iio:device0/in_temp_raw",
        temp_scale_path="/sys/bus/iio/devices/iio:device0/in_temp_scale",
        initial_setpoint=60.0,
        pwm_period=0.5,
        pid_gains=(2.3, 0.25, 2.5)
    ):
        self.temp_raw_path = temp_raw_path
        self.temp_scale_path = temp_scale_path
        self.setpoint = initial_setpoint
        
        # PID setup
        Kp, Ki, Kd = pid_gains
        self.pid = PID(Kp, Ki, Kd, setpoint=self.setpoint)
        self.pid.output_limits = (0, pwm_period)
    
    def read_temperature(self):
        """Read temperature from sensor with retry logic"""
        import time
        
        for attempt in range(5):
            try:
                with open(self.temp_raw_path) as f:
                    raw = int(f.read().strip())
                with open(self.temp_scale_path) as f:
                    scale = int(f.read().strip())
                return raw * scale / 1000.0
            except Exception as e:
                if attempt < 4:  # Don't print warning on last attempt
                    print(f"[WARN] Temperature read attempt {attempt + 1} failed: {e}")
                    time.sleep(0.1)  # Brief delay before retry
                else:
                    print(f"[ERROR] Temperature sensor failed after 5 attempts: {e}")
                    raise
    
    def set_target(self, target_temp):
        """Update target temperature"""
        self.setpoint = target_temp
        self.pid.setpoint = target_temp
    
    def calculate_output(self, current_temp):
        """Calculate PID output for current temperature"""
        return self.pid(current_temp)