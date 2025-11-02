#!/usr/bin/env python3
import time

# Global variable to track highest stage reached
_highest_stage_index = 0

def get_roast_stage(temp):
    """Determine roast stage based on temperature, never going backwards"""
    global _highest_stage_index
    
    stages = [
        (0, "Drying"),
        (160, "Maillard"), 
        (200, "First Crack"),
        (205, "Development"),
        (215, "Dark Roast")
    ]
    
    # Determine current stage based on temperature
    current_stage_index = 0
    for i, (temp_threshold, stage_name) in enumerate(stages):
        if temp >= temp_threshold:
            current_stage_index = i
    
    # Only advance, never go backwards
    if current_stage_index > _highest_stage_index:
        _highest_stage_index = current_stage_index
    
    return stages[_highest_stage_index][1]

def reset_roast_stage():
    """Reset stage tracking for new roast"""
    global _highest_stage_index
    _highest_stage_index = 0

def format_elapsed_time(elapsed_seconds):
    """Format elapsed time as MM:SS"""
    return time.strftime("%M:%S", time.gmtime(elapsed_seconds))