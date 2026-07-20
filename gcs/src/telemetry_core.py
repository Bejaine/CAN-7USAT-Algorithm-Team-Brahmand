import serial
import csv
import time
import threading
from queue import Queue

class TelemetryEngine:
    def __init__(self, port, baudrate=9600, team_id="2026-IN-SPACE-CAN-7USAT-008", initial_rx=0, initial_loss=0, expected_tx=None):
        self.port = port
        self.baudrate = baudrate
        self.team_id = team_id
        self.serial_conn = None
        self.is_running = False
        
        self.data_queue = Queue()
        self.csv_filename = f"../data/Flight_{self.team_id}.csv"
        self.setup_csv()
        
        self.gcs_rx_count = initial_rx
        self.expected_tx_count = expected_tx
        self.packets_lost = initial_loss

    def setup_csv(self):
        headers = [
            "TEAM_ID", "TIME_STAMPING", "PACKET_COUNT", "ALTITUDE", 
            "PRESSURE", "TEMP", "VOLTAGE", "GNSS_TIME", "GNSS_LATITUDE", 
            "GNSS_LONGITUDE", "GNSS_ALTITUDE", "GNSS_SATS", "ACCELEROMETER_DATA", 
            "GYRO_SPIN_RATE", "FLIGHT_SOFTWARE_STATE", "OPTIONAL_DATA"
        ]
        with open(self.csv_filename, mode='w', newline='') as file: # Overwrite for testing
            writer = csv.writer(file)
            writer.writerow(headers)

    def connect(self):
        try:
            # We remove the hard timeout limit so it waits for data naturally
            self.serial_conn = serial.Serial(self.port, self.baudrate, timeout=2.0)
            return True
        except serial.SerialException as e:
            return False

    def start_listening(self):
        if not self.serial_conn or not self.serial_conn.is_open:
            if not self.connect(): return
        self.is_running = True
        self.thread = threading.Thread(target=self._read_loop, daemon=True)
        self.thread.start()

    def stop_listening(self):
        self.is_running = False
        if self.serial_conn and self.serial_conn.is_open:
            self.serial_conn.close()

    def send_command(self, command_str):
        if self.serial_conn and self.serial_conn.is_open:
            try:
                full_cmd = f"CMD,{self.team_id},{command_str}\r"
                self.serial_conn.write(full_cmd.encode('ascii'))
                print(f"[CORE TX] Sent: {full_cmd.strip()}")
                return True
            except Exception: pass
        return False

    def _read_loop(self):
        """Bulletproof buffer reader. Never slices packets."""
        buffer = b""
        while self.is_running:
            try:
                # Wait for at least 1 byte, then read everything available
                raw_data = self.serial_conn.read(self.serial_conn.in_waiting or 1)
                
                if raw_data:
                    buffer += raw_data
                    
                    # If we have a full carriage return, extract the complete packets
                    if b'\r' in buffer:
                        packets = buffer.split(b'\r')
                        
                        # The last element in the list is the unfinished remainder 
                        # We put it back in the buffer for the next loop to finish!
                        buffer = packets.pop() 
                        
                        for p in packets:
                            if p: # Ignore empty strings
                                ascii_str = p.decode('ascii', errors='ignore').strip()
                                self._process_packet(ascii_str)
            except Exception as e:
                time.sleep(0.5)

    def _process_packet(self, data_str):
        parts = data_str.split(',')
        if len(parts) == 16:
            # 1. Update Packet Tracking (G16 Requirement)
            self.gcs_rx_count += 1
            try:
                current_tx_count = int(parts[2])
                if self.expected_tx_count is not None:
                    if current_tx_count > self.expected_tx_count:
                        self.packets_lost += (current_tx_count - self.expected_tx_count)
                self.expected_tx_count = current_tx_count + 1
            except ValueError:
                pass

            # 2. Write to CSV safely
            with open(self.csv_filename, mode='a', newline='') as file:
                writer = csv.writer(file)
                writer.writerow(parts)
            
            # 3. Parse Accelerometer (Format is X;Y;Z)
            accel_z = 0.0
            try:
                accel_parts = parts[12].split(';')
                if len(accel_parts) == 3:
                    accel_z = float(accel_parts[2])
            except Exception: pass
            
            # 4. Queue extensive data for the multi-chart UI
            try:
                packet_dict = {
                    "team_id": parts[0],
                    "time": float(parts[1]),
                    "tx_count": int(parts[2]),
                    "rx_count": self.gcs_rx_count,
                    "lost_count": self.packets_lost,
                    "altitude": float(parts[3]),
                    "pressure": float(parts[4]),
                    "temp": float(parts[5]),
                    "voltage": float(parts[6]),
                    "gnss_time": parts[7],
                    "gnss_lat": float(parts[8]),
                    "gnss_lon": float(parts[9]),
                    "gnss_alt": float(parts[10]),
                    "sats": int(parts[11]),
                    "accel_z": accel_z,
                    "gyro_spin": float(parts[13]),
                    "state": int(parts[14])
                }
                self.data_queue.put(packet_dict)
            except ValueError: pass
        else:
            print(f"\n[CORE DEBUG] Ignored Corrupt Serial Frame: {data_str}")

    # def _process_packet(self, data_str):
    #     parts = data_str.split(',')
    #     if len(parts) == 16:
    #         # 1. Update Packet Tracking (G16 Requirement)
    #         self.gcs_rx_count += 1
    #         try:
    #             current_tx_count = int(parts[2])
    #             if self.expected_tx_count is not None:
    #                 # If the CanSat sent #45, but we expected #44, we lost 1 packet over RF
    #                 if current_tx_count > self.expected_tx_count:
    #                     self.packets_lost += (current_tx_count - self.expected_tx_count)
                
    #             # Next expected packet is this one + 1
    #             self.expected_tx_count = current_tx_count + 1
    #         except ValueError:
    #             pass

    #         # 2. Write to CSV safely
    #         with open(self.csv_filename, mode='a', newline='') as file:
    #             writer = csv.writer(file)
    #             writer.writerow(parts)
            
    #         # 3. Queue extensive data for the upcoming multi-chart UI
    #         try:
    #             packet_dict = {
    #                 "time": float(parts[1]),
    #                 "tx_count": int(parts[2]),
    #                 "rx_count": self.gcs_rx_count,
    #                 "lost_count": self.packets_lost,
    #                 "altitude": float(parts[3]),
    #                 "pressure": float(parts[4]),
    #                 "temp": float(parts[5]),
    #                 "voltage": float(parts[6]),
    #                 "sats": int(parts[11]),
    #                 "gyro_spin": float(parts[13]),
    #                 "state": int(parts[14])
    #             }
    #             self.data_queue.put(packet_dict)
    #         except ValueError: pass
    #     else:
    #         print(f"\n[CORE DEBUG] Ignored Corrupt Serial Frame: {data_str}")