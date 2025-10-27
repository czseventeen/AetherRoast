#!/usr/bin/env python3
import sys
import threading
from roast_controller import RoastController

def main():
    if len(sys.argv) < 2:
        print("Usage: python3 main.py <roast_profile.json>")
        sys.exit(1)
    
    roast_profile_file = f"{sys.argv[1]}"
    
    controller = RoastController(
        roast_profile_file=roast_profile_file,
        log_file="roast_log.csv"
    )
    
    try:
        controller.running = True
        control_thread = threading.Thread(target=controller.start)
        control_thread.start()
        
        controller.input_loop()
        
    except KeyboardInterrupt:
        print("\n[INFO] Stopping by user request...")
    
    finally:
        controller.shutdown()

if __name__ == "__main__":
    main()
