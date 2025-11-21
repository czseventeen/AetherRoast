#!/usr/bin/env python3
import time

# Global variables for stage tracking
_current_stage_index = 0
_stage_start_time = None
_stages = ["Drying", "Maillard", "First Crack", "First Crack End", "Second Crack", "Second Crack End"]

def get_roast_stage():
    """Get current roast stage (user-controlled)"""
    return _stages[_current_stage_index]

def get_stage_duration(current_time):
    """Get how long current stage has been running"""
    if _stage_start_time is None:
        return 0
    return current_time - _stage_start_time

def advance_roast_stage(current_time):
    """Advance to next roast stage"""
    global _current_stage_index, _stage_start_time
    if _current_stage_index < len(_stages) - 1:
        _current_stage_index += 1
        _stage_start_time = current_time
    return _stages[_current_stage_index]

def reset_roast_stage(current_time):
    """Reset stage tracking for new roast"""
    global _current_stage_index, _stage_start_time
    _current_stage_index = 0
    _stage_start_time = current_time

def format_elapsed_time(elapsed_seconds):
    """Format elapsed time as MM:SS"""
    return time.strftime("%M:%S", time.gmtime(elapsed_seconds))