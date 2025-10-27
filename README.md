# AetherRoast
A modular Python-based control system for coffee roasting with automated temperature control, fan management, and customizable roast profiles.
Supports temperature profiling, preheat control, and fan modulation via SSR and SPD1168X power supply for precision roast automation.

## Features

- **Automated Temperature Control**: PID-based SSR control for precise heating
- **Fan Speed Management**: Variable DC motor fan control via power supply
- **Preheat Phase**: Automated preheating with user-controlled bean drop timing
- **JSON Roast Profiles**: Customizable temperature curves with individual PID settings
- **Real-time Monitoring**: Live temperature, stage, and control output display
- **CSV Logging**: Detailed roast data logging for analysis

## Hardware Requirements

- Raspberry Pi with GPIO access
- SSR (Solid State Relay) connected to GPIO pin 26
- Temperature sensor (IIO device at `/sys/bus/iio/devices/iio:device0/`)
- Siglent SPD1168X power supply (for fan control)
- DC motor fan (16V, max 1A)

## Installation

```bash
pip install RPi.GPIO simple-pid pyvisa
```

## Usage

```bash
python3 main.py <profile_name>.json
```

Example:
```bash
python3 main.py colombia_huila_light.json
```

## Roast Profile Format

```json
{
  "name": "Profile Name",
  "description": "Profile description",
  "pid_gains": [2.0, 0.3, 2.2],
  "pwm_period": 0.5,
  "preheat": {
    "temp_c": 180
  },
  "roast_profile": [
    [0, 25],
    [60, 110],
    [120, 145],
    [180, 170],
    [240, 190],
    [300, 205]
  ]
}
```

## Project Structure

```
ProfileRoasting_v1/
├── main.py                     # Entry point
├── roast_controller.py         # Main controller orchestration
├── controller/                 # Hardware control modules
│   ├── ssr.py                 # SSR/GPIO control
│   ├── temperature.py         # Temperature sensor & PID
│   ├── fan.py                 # Fan speed control
│   └── spd1168x.py           # Power supply interface
├── utils/                      # Utility functions
│   ├── logging.py             # CSV data logging
│   └── helpers.py             # Stage detection & formatting
└── profiles/                   # Roast profiles
    ├── profile_loader.py      # JSON profile loading
    └── *.json                 # Profile files
```

## Control Flow

1. **Preheat Phase**: 
   - Fan at 100% speed
   - Heat to target temperature (default 180°C)
   - Reduce fan to 20% when target reached
   - Wait for user to press ENTER (bean drop)

2. **Roast Phase**:
   - Fan at 100% speed
   - Follow temperature profile with PID control
   - Log data and display real-time status

3. **Shutdown**:
   - Turn off SSR and fan
   - Close all connections
   - Save log data

## Safety Features

- Automatic shutdown on Ctrl+C
- GPIO cleanup on exit
- Power supply safety controls
- Error handling for hardware failures

## Roast Stages

- **Drying**: < 160°C
- **Maillard**: 160-190°C  
- **First Crack**: 190-205°C
- **Development**: 205-215°C
- **Dark Roast**: > 215°C
