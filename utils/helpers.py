#!/usr/bin/env python3
import time

def get_roast_stage(temp):
    """Determine roast stage based on temperature"""
    if temp < 160:
        return "Drying"
    elif temp < 190:
        return "Maillard"
    elif temp < 205:
        return "First Crack"
    elif temp <= 215:
        return "Development"
    else:
        return "Dark Roast"

def format_elapsed_time(elapsed_seconds):
    """Format elapsed time as MM:SS"""
    return time.strftime("%M:%S", time.gmtime(elapsed_seconds))