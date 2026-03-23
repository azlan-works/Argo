import smbus2
import time
import sys
import os
from collections import deque

I2C_BUS = 1
I2C_ADDR = 0x6A

# Registers
REG_ADC_CTRL = 0x02
REG_VBAT = 0x0E
REG_VBUS = 0x11

# ADC control
BYTE_ADC_START_ONESHOT = 0x9D
BYTE_ADC_STOP = 0x1D

# Conversion constants
VBAT_OFFSET = 2.304
VBAT_LSB = 0.020
VBUS_OFFSET = 2.600
VBUS_LSB = 0.100

# Detection tuning
WINDOW = 6
MIN_BAT_NONZERO = 4
STUCK_SPAN_MV = 20
VBUS_PRESENT_MIN_CODE = 2

def _convert_vbat(raw_byte):
    code = raw_byte & 0x7F
    voltage = VBAT_OFFSET + code * VBAT_LSB
    return voltage, code

def _convert_vbus(raw_byte):
    code = raw_byte & 0x7F
    voltage = VBUS_OFFSET + code * VBUS_LSB
    return voltage, code

def _is_battery_present(vbat_codes, vbus_codes):
    if not vbat_codes:
        return False

    nonzero_count = sum(1 for c in vbat_codes if c > 0)
    if nonzero_count < MIN_BAT_NONZERO:
        return False

    vbus_present_any = any(c >= VBUS_PRESENT_MIN_CODE for c in vbus_codes)
    if vbus_present_any:
        nz = [c for c in vbat_codes if c > 0]
        if len(nz) >= 3:
            vmin = min(nz)
            vmax = max(nz)
            if (vmax - vmin) * 20 <= STUCK_SPAN_MV:
                return False

    return True

def read_power_voltage_realtime():
    bus = None
    try:
        bus = smbus2.SMBus(I2C_BUS)

        vbat_hist = deque(maxlen=WINDOW)
        vbus_hist = deque(maxlen=WINDOW)

        print(f"BQ25895 monitor started (I2C Bus {I2C_BUS}, Addr 0x{I2C_ADDR:X})")
        print("Minimal-write mode: one-shot ADC trigger only")
        print("Presence logic: debounced + stale-VBAT rejection")
        print("Press Ctrl+C to stop")
        print("-" * 95)

        while True:
            bus.write_byte_data(I2C_ADDR, REG_ADC_CTRL, BYTE_ADC_START_ONESHOT)
            time.sleep(0.10)

            vbat_raw = bus.read_byte_data(I2C_ADDR, REG_VBAT)
            vbus_raw = bus.read_byte_data(I2C_ADDR, REG_VBUS)

            bus.write_byte_data(I2C_ADDR, REG_ADC_CTRL, BYTE_ADC_STOP)

            vbat_v, vbat_code = _convert_vbat(vbat_raw)
            vbus_v, vbus_code = _convert_vbus(vbus_raw)

            vbat_hist.append(vbat_code)
            vbus_hist.append(vbus_code)

            vbus_present = vbus_code >= VBUS_PRESENT_MIN_CODE
            battery_present = _is_battery_present(list(vbat_hist), list(vbus_hist))

            if battery_present and vbus_present:
                msg = (
                    f"\rPower: BATTERY + VBUS | "
                    f"VBAT: {vbat_v:.3f} V (raw {vbat_code}/0x{vbat_code:02X}) | "
                    f"VBUS: {vbus_v:.3f} V (raw {vbus_code}/0x{vbus_code:02X})"
                )
            elif battery_present and not vbus_present:
                msg = (
                    f"\rPower: BATTERY ONLY | "
                    f"VBAT: {vbat_v:.3f} V (raw {vbat_code}/0x{vbat_code:02X}) | "
                    f"VBUS: not present (raw {vbus_code}/0x{vbus_code:02X})"
                )
            elif (not battery_present) and vbus_present:
                msg = (
                    f"\rPower: VBUS ONLY | "
                    f"VBUS: {vbus_v:.3f} V (raw {vbus_code}/0x{vbus_code:02X}) | "
                    f"VBAT: ignored/stale (raw {vbat_code}/0x{vbat_code:02X})"
                )
            else:
                msg = (
                    f"\rPower: NONE/UNKNOWN | "
                    f"VBAT raw {vbat_code}/0x{vbat_code:02X}, "
                    f"VBUS raw {vbus_code}/0x{vbus_code:02X}"
                )

            sys.stdout.write(msg)
            sys.stdout.flush()
            time.sleep(0.4)

    except KeyboardInterrupt:
        sys.stdout.write("\nMonitoring stopped by user.\n")
    except FileNotFoundError:
        sys.stdout.write(f"\nError: I2C Bus /dev/i2c-{I2C_BUS} not found.\n")
    except Exception as e:
        sys.stdout.write(f"\nI2C communication error: {e}\n")
    finally:
        if bus is not None:
            try:
                bus.close()
            except Exception:
                pass

if __name__ == "__main__":
    os.system("cls" if os.name == "nt" else "clear")
    read_power_voltage_realtime()
