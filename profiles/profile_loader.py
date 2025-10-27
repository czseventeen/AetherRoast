#!/usr/bin/env python3
import json
import os
import sys

class RoastProfile:
    def __init__(self, profile_file=None):
        if profile_file:
            self.load_profile(profile_file)
    
    def load_profile(self, file_path):
        """Load roast profile from JSON file"""
        if not os.path.exists(file_path):
            print(f"[ERROR] Roast profile file not found: {file_path}")
            sys.exit(1)
        
        with open(file_path, 'r') as f:
            data = json.load(f)
        
        self.name = data.get("name", "")
        self.description = data.get("description", "")
        self.pid_gains = tuple(data.get("pid_gains", [2.3, 0.25, 2.5]))
        self.pwm_period = data.get("pwm_period", 0.5)
        self.preheat = data.get("preheat")
        self.profile_data = [(float(point[0]), float(point[1])) for point in data["roast_profile"]]
        
        self.profile_data.sort(key=lambda x: x[0])
        print(f"[INFO] Loaded profile '{self.name}': {len(self.profile_data)} points")
    
    def interpolate_setpoint(self, elapsed):
        """Interpolate target temperature for given elapsed time"""
        if not self.profile_data or elapsed <= self.profile_data[0][0]:
            return self.profile_data[0][1] if self.profile_data else 60.0
        
        for i in range(1, len(self.profile_data)):
            t0, temp0 = self.profile_data[i - 1]
            t1, temp1 = self.profile_data[i]
            if elapsed <= t1:
                ratio = (elapsed - t0) / (t1 - t0)
                return temp0 + ratio * (temp1 - temp0)
        
        return self.profile_data[-1][1]