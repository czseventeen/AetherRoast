#!/usr/bin/env python3
import csv
import time

class RoastLogger:
    def __init__(self, log_file="roast_log.csv"):
        self.log_file = log_file
        self.log_fh = None
        self.csv_writer = None
        self.init_log()
    
    def init_log(self):
        """Initialize CSV log file with headers"""
        self.log_fh = open(self.log_file, "w", newline="")
        self.csv_writer = csv.writer(self.log_fh)
        self.csv_writer.writerow([
            "timestamp_sec",
            "elapsed_sec", 
            "elapsed_mmss",
            "stage",
            "target_temp_C",
            "actual_temp_C",
            "pid_on_time_s"
        ])
    
    def log_step(self, elapsed, stage, target_temp, actual_temp, on_time):
        """Log a single roasting step"""
        mmss = time.strftime("%M:%S", time.gmtime(elapsed))
        self.csv_writer.writerow([
            time.time(), elapsed, mmss, stage, target_temp, actual_temp, on_time
        ])
        self.log_fh.flush()
    
    def close(self):
        """Close log file"""
        if self.log_fh:
            self.log_fh.close()