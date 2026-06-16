# src/telemetry_core.py
import serial
import csv
import time
import threading
from queue import Queue

class TelemetryEngine:
    def __init__(self, port, baudrate=9600, team_id="2026-IN-SPACE-CAN-7USAT-008"):
        self.port = port
        self.baudrate = baudrate
        self.team_id = team_id
        self.serial_conn = None
        self.is_running = False
        
        # Thread-safe queue to pass parsed data to the UI
        self.data_queue = Queue()
        
        # Setup CSV Logging
        self.csv_filename = f"../data/Flight_{self.team_id}.csv"
        self.setup_csv()

    def setup_csv(self):
        """Creates the CSV file and writes the mandatory headers."""
        headers = [
            "TEAM_ID", "TIME_STAMPING", "PACKET_COUNT", "ALTITUDE", 
            "PRESSURE", "TEMP", "VOLTAGE", "GNSS_TIME", "GNSS_LATITUDE", 
            "GNSS_LONGITUDE", "GNSS_ALTITUDE", "GNSS_SATS", "ACCELEROMETER_DATA", 
            "GYRO_SPIN_RATE", "FLIGHT_SOFTWARE_STATE", "OPTIONAL_DATA"
        ]
        with open(self.csv_filename, mode='a', newline='') as file:
            writer = csv.writer(file)
            writer.writerow(headers)
        print(f"[CORE] Logging initialized to {self.csv_filename}")

    def connect(self):
        """Attempts to open the serial port."""
        try:
            self.serial_conn = serial.Serial(self.port, self.baudrate, timeout=1)
            print(f"[CORE] Successfully connected to {self.port}")
            return True
        except serial.SerialException as e:
            print(f"[CORE] Connection Failed: {e}")
            return False

    def start_listening(self):
        """Starts the background listening thread."""
        if not self.serial_conn or not self.serial_conn.is_open:
            if not self.connect():
                return
                
        self.is_running = True
        self.thread = threading.Thread(target=self._read_loop, daemon=True)
        self.thread.start()
        print("[CORE] Background telemetry thread running...")

    def stop_listening(self):
        self.is_running = False
        if self.serial_conn and self.serial_conn.is_open:
            self.serial_conn.close()
        print("[CORE] Connection closed.")

    def send_command(self, command_str):
        """Sends a command string to the CANSAT over the serial port."""
        if self.serial_conn and self.serial_conn.is_open:
            try:
                # Append carriage return/newline as is standard for serial parsing
                full_cmd = f"CMD,{self.team_id},{command_str}\r"
                self.serial_conn.write(full_cmd.encode('ascii'))
                print(f"[CORE TX] Sent: {full_cmd.strip()}")
                return True
            except Exception as e:
                print(f"[CORE ERROR] Failed to send command: {e}")
                return False
        print("[CORE WARNING] Cannot send command. Port not open.")
        return False

    def _read_loop(self):
        """The core loop that runs in the background. It must NEVER crash."""
        while self.is_running:
            try:
                # Read until the carriage return '\r' as per guidelines
                raw_data = self.serial_conn.read_until(b'\r')
                
                if raw_data:
                    ascii_str = raw_data.decode('ascii', errors='ignore').strip()
                    self._process_packet(ascii_str)
                    
            except Exception as e:
                print(f"[CORE WARNING] Read error: {e}")
                time.sleep(0.5) # Prevent CPU spinning on hard disconnect

    def _process_packet(self, data_str):
        """Splits the CSV string, logs it, and pushes to UI queue."""
        parts = data_str.split(',')
        
        # The guidelines dictate 16 fields
        if len(parts) == 16:
            # 1. Log to official CSV file immediately
            with open(self.csv_filename, mode='a', newline='') as file:
                writer = csv.writer(file)
                writer.writerow(parts)
            
            # 2. Parse out a few key values for the UI
            try:
                packet_dict = {
                    "time": float(parts[1]),
                    "altitude": float(parts[3]),
                    "state": int(parts[14])
                }
                self.data_queue.put(packet_dict)
            except ValueError:
                pass # Ignore corrupted float conversions

# --- Quick Test Block ---
if __name__ == "__main__":
    import sys
    if len(sys.argv) < 2:
        print("Usage: python telemetry_core.py <PORT>")
        print("Example: python telemetry_core.py /dev/pts/3")
        sys.exit(1)
        
    engine = TelemetryEngine(port=sys.argv[1])
    engine.start_listening()
    
    try:
        while True:
            # Just print what the engine puts in the queue to verify it works
            while not engine.data_queue.empty():
                data = engine.data_queue.get()
                print(f"[UI WOULD SEE] Time: {data['time']}s | Alt: {data['altitude']}m | State: {data['state']}")
            time.sleep(0.1)
    except KeyboardInterrupt:
        engine.stop_listening()