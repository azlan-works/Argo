import time
import struct
import threading
import queue
import sys
from smbus2 import SMBus
import numpy as np 

# --- CONFIGURATION & CONSTANTS ---
I2C_ADDR = 0x6B
# Register addresses
REG_WHO_AM_I = 0x0F
REG_CTRL2_G = 0x11
REG_CTRL3_C = 0x12
REG_CTRL6_G = 0x15
REG_OUTX_L_G = 0x22
# Sensitivity for ±2000 dps full-scale (70 mdps/LSB)
SENSITIVITY_DPS = 0.07 

# --- GLOBAL STATE ---
data_queue = queue.Queue()
position_deg = np.array([0.0, 0.0, 0.0]) # [Roll, Pitch, Yaw]
last_time = None
bias_dps = np.array([0.0, 0.0, 0.0]) 

# --- SENSOR READER THREAD ---

class SensorReader(threading.Thread):
    def __init__(self, bus):
        super().__init__()
        self.bus = bus
        self.running = True
        self.daemon = True 

    def setup_sensor(self):
        """Configures the LSM6DSV16X Gyroscope."""
        if self.bus.read_byte_data(I2C_ADDR, REG_WHO_AM_I) != 0x70:
            raise IOError(f"LSM6DSV16X not found at {I2C_ADDR:#02x}")

        # Set Gyro ODR to 120 Hz, Full-Scale to ±2000 dps, Enable BDU/IF_INC
        self.bus.write_byte_data(I2C_ADDR, REG_CTRL2_G, 0x06)
        self.bus.write_byte_data(I2C_ADDR, REG_CTRL6_G, 0x04)
        self.bus.write_byte_data(I2C_ADDR, REG_CTRL3_C, 0x44)
        time.sleep(0.1)

    def read_dps(self):
        """Reads raw data, converts to dps, and returns (dps_x, dps_y, dps_z)."""
        raw_data = self.bus.read_i2c_block_data(I2C_ADDR, REG_OUTX_L_G, 6)

        # Unpack as 3 16-bit signed little-endian integers
        raw_x, raw_y, raw_z = struct.unpack('<hhh', bytearray(raw_data))

        # Convert raw LSBs to degrees per second (dps)
        return raw_x * SENSITIVITY_DPS, raw_y * SENSITIVITY_DPS, raw_z * SENSITIVITY_DPS

    def run(self):
        try:
            self.setup_sensor()
            while self.running:
                dps_x, dps_y, dps_z = self.read_dps()
                sample_time = time.time()

                # Push angular velocity vector and timestamp to queue
                data_queue.put( (dps_x, dps_y, dps_z, sample_time) )

                time.sleep(0.01) # Target ~100 Hz sampling

        except Exception as e:
            data_queue.put(None) 
            print(f"\nError in sensor thread: {e}", file=sys.stderr)

    def stop(self):
        self.running = False


# --- INTEGRATION & DISPLAY ---

def integrate_and_show():
    """Processes queue data, integrates position, and updates CLI display."""
    global position_deg, last_time, bias_dps
    
    new_data_processed = False
    
    # Process all available new data
    while not data_queue.empty():
        try:
            new_data = data_queue.get_nowait()
        except queue.Empty:
            break

        if new_data is None: 
            return False # Shutdown signal

        dps_x, dps_y, dps_z, current_time = new_data
        dps_vector = np.array([dps_x, dps_y, dps_z]) - bias_dps

        if last_time is not None:
            dt = current_time - last_time
            position_deg += dps_vector * dt
            new_data_processed = True

        last_time = current_time
   if new_data_processed:
        roll, pitch, yaw = position_deg
        # Use \r and \033[K to clear line and print
        sys.stdout.write(f"\rRoll (X): {roll:9.2f}° | Pitch (Y): {pitch:9.2f}° | Yaw (Z): {yaw:9.2f}°")
        sys.stdout.flush()

    return True

def calibrate(duration_sec=3):
    """Calculates gyro bias by averaging stationary readings."""
    global bias_dps
    
    print(f"Starting calibration ({duration_sec}s). KEEP SENSOR STILL...")
    
    samples = []
    start_time = time.time()
    
    while not data_queue.empty(): data_queue.get_nowait()

    while time.time() - start_time < duration_sec:
        try:
            dps_x, dps_y, dps_z, _ = data_queue.get(timeout=0.02)
            samples.append(np.array([dps_x, dps_y, dps_z]))
        except queue.Empty:
            pass 
        except Exception:
            raise IOError("Sensor error during calibration.")

    if not samples:
        raise IOError("No sensor data received during calibration.")

    bias_dps = np.mean(samples, axis=0)
    
    print("\rCalibration complete. Gyro Bias (dps):")
    print(f"  X (Roll): {bias_dps[0]:.4f}, Y (Pitch): {bias_dps[1]:.4f}, Z (Yaw): {bias_dps[2]:.4f}")
    print("---------------------------------------------------------------------")


# --- MAIN EXECUTION ---

if __name__ == "__main__":
    sensor_thread = None
    i2c_bus = None
    
    print("LSM6DSV16X Gyroscope Position Tracker (CLI)")
    print("Press Ctrl+C to stop.")
    print("---------------------------------------------------------------------")
    print("Note: This simple integration WILL drift slowly over time.")
    print("---------------------------------------------------------------------")

    try:
        i2c_bus = SMBus(1)
        sensor_thread = SensorReader(i2c_bus)
        sensor_thread.start()

        time.sleep(1.0) # Wait for thread setup

        calibrate()

        while True:
            if not integrate_and_show():
                break 
            time.sleep(0.05) 

    except FileNotFoundError:
        print("\n\nI2C Error: Bus not found. Check permissions or I2C enablement.")
    except IOError as e:
        print(f"\n\nStartup Error: {e}")
    except KeyboardInterrupt:
        print("\n\nStopping...")
    except Exception as e:
        print(f"\n\nAn unexpected error occurred: {e}")

    finally:
        if sensor_thread and sensor_thread.running:
            sensor_thread.stop()
            sensor_thread.join()
        if i2c_bus:
            i2c_bus.close()
        print("Tracker stopped and resources released.")      
