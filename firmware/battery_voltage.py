import smbus2
import time
import sys
import os

# --- I2C and Chip Configuration ---
I2C_BUS = 10
I2C_ADDR = 0x6a

# Register Definitions (from your code)
REG_ILIM = 0x00
REG_SYSMIN = 0x03
REG_ICHG = 0x04
REG_WATCHDOG = 0x07
REG_BATFET = 0x09
REG_ADC_CTRL = 0x02
REG_VBAT = 0x0E  # **Using 0x0E as per your code's definition**

# Byte Definitions (from your code)
BYTE_INIT_CONFIG = {
    REG_WATCHDOG: 0x8D, # Stop Watchdog timer (0b10001101)
    REG_ILIM:     0x00, # Input limit disabled
    REG_ICHG:     0x08, # 0.5A charging current limit
    REG_BATFET:   0x48, # BATFET control settings (0b01001000)
    REG_SYSMIN:   0x30  # Vsys_min = 3.5V (0b00110000)
}
BYTE_ADC_START = 0x9D  # Start One-Shot Conversion
BYTE_ADC_STOP = 0x1D   # Stop Conversion

# Conversion Constants
VOLTAGE_OFFSET = 2.304
VOLTAGE_LSB = 0.020 # 20 mV per LSB

def _vbat_convert(raw_byte):
    """Converts the raw ADC byte into battery voltage using arithmetic."""
    adc_code = raw_byte & 0x7F
    # Formula: V_BAT = (ADC_Code * 0.020V) + 2.304V
    voltage = (adc_code * VOLTAGE_LSB) + VOLTAGE_OFFSET
    return voltage, adc_code

def read_battery_voltage_realtime():
    try:
        bus = smbus2.SMBus(I2C_BUS)
        
        # 1. Initialize Registers (Run once)
        for reg, byte in BYTE_INIT_CONFIG.items():
            bus.write_byte_data(I2C_ADDR, reg, byte)
            
        print(f"BQ25895 monitoring started (I2C Bus {I2C_BUS}, Addr 0x{I2C_ADDR:X}).")
        print("Press Ctrl+C to stop.")
        print("-" * 35)

        while True:
            # 2. Start One-Shot ADC Conversion
            bus.write_byte_data(I2C_ADDR, REG_ADC_CTRL, BYTE_ADC_START)
            
            # Wait for conversion to complete (25ms is typical, 100ms is safe)
            time.sleep(0.1)
            
            # 3. Read the VBAT ADC Register
            vbat_byte = bus.read_byte_data(I2C_ADDR, REG_VBAT)
            
            # 4. Stop ADC Conversion (to return to low-power mode)
            bus.write_byte_data(I2C_ADDR, REG_ADC_CTRL, BYTE_ADC_STOP)

            # 5. Convert and Display
            voltage, raw_code = _vbat_convert(vbat_byte)
            
            # Use carriage return to update the same line
            sys.stdout.write(f"\rBattery Voltage: {voltage:.3f} V | Raw Code: {raw_code} (0x{raw_code:X})")
            sys.stdout.flush()

            # 6. Wait for the next update cycle (Total loop time ~0.5s)
            time.sleep(0.4)

    except KeyboardInterrupt:
        sys.stdout.write("\nMonitoring stopped by user.\n")
    except FileNotFoundError:
        sys.stdout.write(f"\nError: I2C Bus /dev/i2c-{I2C_BUS} not found.\n")
    except Exception as e:
        sys.stdout.write(f"\nAn I2C communication error occurred: {e}\n")
    finally:
        # Ensure the bus is closed if necessary (smbus2 handles this implicitly)
        pass

if __name__ == '__main__':
    # Clear the terminal before starting for a clean look
    os.system('cls' if os.name == 'nt' else 'clear') 
    read_battery_voltage_realtime()
