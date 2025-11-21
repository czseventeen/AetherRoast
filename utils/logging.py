#!/usr/bin/env python3
import csv
import time

class RoastLogger:
    def __init__(self, log_file="roast_log.csv", profile_name=None):
        self.log_file = log_file
        self.profile_name = profile_name
        self.log_fh = None
        self.csv_writer = None
        self.init_log()
    
    def init_log(self):
        """Initialize CSV log file with headers"""
        self.log_fh = open(self.log_file, "w", newline="")
        self.csv_writer = csv.writer(self.log_fh)
        
        # Add profile name as comment if available
        if self.profile_name:
            self.log_fh.write(f"# Profile: {self.profile_name}\n")
        
        self.csv_writer.writerow([
            "elapsed_mmss_mmm",
            "stage",
            "stage_duration_mmss_mmm",
            "target_temp_C",
            "actual_temp_C",
            "pid_on_time_s"
        ])
    
    def log_step(self, elapsed, stage, stage_duration, target_temp, actual_temp, on_time):
        """Log a single roasting step"""
        from utils.helpers import format_elapsed_time
        mmss_mmm = format_elapsed_time(elapsed)
        stage_mmss_mmm = format_elapsed_time(stage_duration)
        self.csv_writer.writerow([
            mmss_mmm, stage, stage_mmss_mmm, round(target_temp, 1), round(actual_temp, 2), round(on_time, 2)
        ])
        self.log_fh.flush()
    
    def close(self):
        """Close log file"""
        if self.log_fh:
            self.log_fh.close()