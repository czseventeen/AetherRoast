#!/usr/bin/env python3
import time
import threading
from controller.ssr import SSRController
from controller.temperature import TemperatureController
from utils.logging import RoastLogger
from utils.helpers import get_roast_stage, format_elapsed_time
from profiles.profile_loader import RoastProfile

class RoastController:
    def __init__(self, ssr_pin=26, roast_profile_file=None, log_file="roast_log.csv"):
        # Load profile first to get PID gains and PWM period
        self.profile = RoastProfile(roast_profile_file)
        
        self.ssr = SSRController(ssr_pin, self.profile.pwm_period)
        self.temp_controller = TemperatureController(
            pwm_period=self.profile.pwm_period,
            pid_gains=self.profile.pid_gains
        )
        self.logger = RoastLogger(log_file)
        
        self.running = False
        self.start_time = None
        self.preheat_complete = False
    
    def control_step(self):
        """Execute one control step"""
        elapsed = time.time() - self.start_time if self.start_time else 0
        
        # Update setpoint from profile if available
        if self.profile.profile_data:
            target_temp = self.profile.interpolate_setpoint(elapsed)
            self.temp_controller.set_target(target_temp)
        
        # Read temperature and calculate output
        current_temp = self.temp_controller.read_temperature()
        on_time = self.temp_controller.calculate_output(current_temp)
        stage = get_roast_stage(current_temp)
        
        # Console output
        mmss = format_elapsed_time(elapsed)
        print(f"Elapsed: {mmss} | Stage: {stage} | Temp: {current_temp:.2f}°C | "
              f"Target: {self.temp_controller.setpoint:.2f}°C | SSR ON: {on_time:.2f}s")
        
        # Log data
        self.logger.log_step(elapsed, stage, self.temp_controller.setpoint, current_temp, on_time)
        
        # Control SSR
        self.ssr.control_output(on_time)
    
    def preheat_step(self, target_temp):
        """Execute one preheat control step"""
        current_temp = self.temp_controller.read_temperature()
        on_time = self.temp_controller.calculate_output(current_temp)
        
        print(f"Preheat | Temp: {current_temp:.2f}°C | Target: {target_temp:.1f}°C | SSR ON: {on_time:.2f}s")
        
        self.ssr.control_output(on_time)
        return current_temp >= target_temp - 2.0  # Within 2°C tolerance
    
    def start(self):
        """Start the roasting control loop"""
        self.running = True
        
        try:
            # Preheat phase if configured
            if self.profile.preheat:
                self.preheat_phase()
            
            # Start roasting phase only if still running
            if not self.running:
                return
                
            self.start_time = time.time()
            print(f"[INFO] Starting roast phase for '{self.profile.name}'")
            
            while self.running:
                self.control_step()
        except Exception as e:
            print(f"[ERROR] {e}")
        finally:
            self.shutdown()
    
    def preheat_phase(self):
        """Handle preheat phase"""
        preheat_temp = self.profile.preheat["temp_c"]
        self.temp_controller.set_target(preheat_temp)
        print(f"[INFO] Starting preheat to {preheat_temp}°C... Press ENTER when beans are dropped.")
        
        # Start input thread immediately
        input_thread = threading.Thread(target=self.wait_for_bean_drop)
        input_thread.start()
        
        # Continue heating until user presses enter
        while self.running and not self.preheat_complete:
            self.preheat_step(preheat_temp)
        
        input_thread.join(timeout=0.1)
    
    def wait_for_bean_drop(self):
        """Wait for user to press enter indicating beans are dropped"""
        try:
            input()
            if self.running:  # Only set if still running
                self.preheat_complete = True
                print("[INFO] Beans dropped! Starting roast profile...")
        except (EOFError, KeyboardInterrupt):
            self.shutdown()
    
    def shutdown(self):
        """Shutdown the controller safely"""
        if not self.running:
            return
        
        print("[INFO] Shutting down controller...")
        self.running = False
        self.ssr.turn_off()
        self.ssr.cleanup()
        self.logger.close()
        print(f"[INFO] System shut down safely. SSR OFF. Log saved.")
    
