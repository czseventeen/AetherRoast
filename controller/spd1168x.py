import time
import pyvisa

class SPD1168X:
    """
    A Python class for controlling the Siglent SPD1168X power supply via USB.
    Supports controlling current as an absolute value or percentage of max_current.
    """
    def __init__(self, resource_address=None, max_current=1.0):
        """
        Initializes the power supply object.

        Args:
            resource_address (str, optional): The specific VISA resource address.
                                              If None, it will attempt to find a USB instrument automatically.
            max_current (float, optional): Maximum current allowed for percentage control (A). Default 1.0A.
        """
        self.rm = pyvisa.ResourceManager()
        self.power_supply = None
        self.resource_address = resource_address
        self.max_current = max_current

        try:
            if not self.resource_address:
                usb_resources = self.rm.list_resources("USB?*INSTR")
                if not usb_resources:
                    raise pyvisa.errors.VisaIOError("No USB instruments found.")
                self.resource_address = usb_resources[0]

            self.power_supply = self.rm.open_resource(self.resource_address)
            self.power_supply.write_termination = '\n'
            self.power_supply.read_termination = '\n'
            print(f"Connected to: {self.idn().strip()}")

        except (pyvisa.errors.VisaIOError, Exception) as e:
            print(f"Failed to connect to the instrument: {e}")
            self.power_supply = None
            if hasattr(self, 'rm'):
                try:
                    self.rm.close()
                except:
                    pass

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        if self.power_supply:
            self.close()

    def is_connected(self):
        return self.power_supply is not None

    def idn(self):
        if not self.is_connected():
            return "Not Connected"
        return self.power_supply.query('*IDN?')

    def set_output(self, channel, voltage, current=None, current_pct=None):
        """
        Sets voltage and current. Either provide 'current' in Amps or 'current_pct' 0-100% of max_current.

        Args:
            channel (int): Channel number (1, 2, ...)
            voltage (float): Voltage in volts
            current (float, optional): Absolute current in amps
            current_pct (float, optional): Percentage of max_current (0-100)
        """
        if not self.is_connected():
            return

        if current_pct is not None:
            current = (current_pct / 100.0) * self.max_current

        if current is None:
            current = self.max_current  # default to max if nothing provided

        print(f"Setting Channel {channel}: {voltage}V, {current:.3f}A ({current_pct if current_pct else 100}%)")
        self.power_supply.write(f'CH{channel}:VOLT {voltage}')
        time.sleep(0.1)
        self.power_supply.write(f'CH{channel}:CURR {current}')
        time.sleep(0.1)

    def output_on(self, channel):
        if not self.is_connected():
            return
        print(f"Turning ON Channel {channel}...")
        self.power_supply.write(f'OUTP CH{channel},ON')
        time.sleep(0.1)

    def output_off(self, channel):
        if not self.is_connected():
            return
        print(f"Turning OFF Channel {channel}...")
        self.power_supply.write(f'OUTP CH{channel},OFF')
        time.sleep(0.1)

    def measure_voltage(self, channel):
        if not self.is_connected():
            return None
        return float(self.power_supply.query(f'MEASure:VOLTage? CH{channel}'))

    def measure_current(self, channel):
        if not self.is_connected():
            return None
        return float(self.power_supply.query(f'MEASure:CURRent? CH{channel}'))

    def close(self):
        if self.power_supply:
            self.power_supply.close()
            print("Connection closed.")
            self.power_supply = None

