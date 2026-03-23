import smbus2
import time
import sys

I2C_BUS = 1
I2C_ADDR = 0x6A

# Registers
REG_ADC_CTRL = 0x02
REG_VBAT = 0x0E
REG_VBUS = 0x11
REG_STATUS_0B = 0x0B  # PG_STAT + CHRG_STAT

# ADC control
BYTE_ADC_START_ONESHOT = 0x9D
BYTE_ADC_STOP = 0x1D

# REG0B bits
MASK_PG_STAT = 0x04
MASK_CHRG_STAT = 0x18
SHIFT_CHRG_STAT = 3

# Conversion constants
VBAT_OFFSET = 2.304
VBAT_LSB = 0.020
VBUS_OFFSET = 2.600
VBUS_LSB = 0.100


def convert_vbat(raw):
    code = raw & 0x7F
    return VBAT_OFFSET + code * VBAT_LSB, code


def convert_vbus(raw):
    code = raw & 0x7F
    return VBUS_OFFSET + code * VBUS_LSB, code


def decode_status_0b(status):
    pg = (status & MASK_PG_STAT) != 0
    chrg = (status & MASK_CHRG_STAT) >> SHIFT_CHRG_STAT
    return pg, chrg  # chrg: 0=not charging,1=pre,2=fast,3=done


def estimate_percent(vbat):
    # Simple Li-ion estimate. Adjust if needed.
    lo, hi = 3.30, 4.20
    pct = int((vbat - lo) * 100 / (hi - lo))
    return max(0, min(100, pct))


def main():
    bus = None
    try:
        bus = smbus2.SMBus(I2C_BUS)
        print("Battery percent monitor started. Press Ctrl+C to stop.")
        print("-" * 60)

        while True:
            # Trigger one-shot ADC
            bus.write_byte_data(I2C_ADDR, REG_ADC_CTRL, BYTE_ADC_START_ONESHOT)
            time.sleep(0.10)

            vbat_raw = bus.read_byte_data(I2C_ADDR, REG_VBAT)
            vbus_raw = bus.read_byte_data(I2C_ADDR, REG_VBUS)
            status = bus.read_byte_data(I2C_ADDR, REG_STATUS_0B)

            bus.write_byte_data(I2C_ADDR, REG_ADC_CTRL, BYTE_ADC_STOP)

            vbat_v, vbat_code = convert_vbat(vbat_raw)
            vbus_v, vbus_code = convert_vbus(vbus_raw)
            pg_stat, chrg_stat = decode_status_0b(status)

            vbus_present = (vbus_code > 0) or pg_stat

            # Battery is "trusted" if charging state says so OR no VBUS and VBAT is valid
            battery_present = (chrg_stat in (1, 2, 3)) or ((not vbus_present) and (vbat_code > 0))

            emojis = ""
            if vbus_present:
                emojis += "🔌"
            if chrg_stat in (1, 2):
                emojis += "⚡"

            if battery_present:
                pct = estimate_percent(vbat_v)
                line = f"\r{emojis} Battery: {pct}% ({vbat_v:.3f}V)"
            elif vbus_present:
                line = f"\r{emojis} External power only"
            else:
                line = "\r❓ Power state unknown"

            sys.stdout.write(line + " " * 8)
            sys.stdout.flush()
            time.sleep(0.5)

    except KeyboardInterrupt:
        sys.stdout.write("\nStopped by user.\n")
    except Exception as e:
        sys.stdout.write(f"\nError: {e}\n")
    finally:
        if bus is not None:
            try:
                bus.close()
            except Exception:
                pass


if __name__ == "__main__":
    main()
