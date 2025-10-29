#!/usr/bin/env python3
from .spd1168x import SPD1168X

class FanController:
    def __init__(self, channel=1, voltage=16.0, max_current=1.0):
        self.channel = channel
        self.voltage = voltage
        self.max_current = max_current
        self.power_supply = None
        self.is_on = False
        
        try:
            self.power_supply = SPD1168X(max_current=max_current)
            if self.power_supply.is_connected():
                self.power_supply.set_output(channel, voltage, current_pct=0)
                print(f"[INFO] Fan controller initialized on channel {channel}")
        except Exception as e:
            print(f"[WARN] Fan controller not available: {e}")
            self.power_supply = None
    
    def set_speed(self, percentage):
        """Set fan speed as percentage (0-100)"""
        if not self.power_supply or not self.power_supply.is_connected():
            print(f"[WARN] Fan control unavailable - requested {percentage}%")
            return
            
        try:
            self.power_supply.set_output(self.channel, self.voltage, current_pct=percentage)
            if not self.is_on:
                self.power_supply.output_on(self.channel)
                self.is_on = True
            print(f"[INFO] Fan speed set to {percentage}%")
        except Exception as e:
            print(f"[ERROR] Fan/Power supply control failed: {e}")
            self.power_supply = None  # Mark as disconnected
    
    def shutdown(self):
        """Turn off fan and close connection"""
        try:
            if self.power_supply and self.power_supply.is_connected():
                self.power_supply.output_off(self.channel)
                self.power_supply.close()
                print("[INFO] Fan controller shut down")
        except Exception as e:
            print(f"[WARN] Fan shutdown failed: {e}")