# src/teensy_mock.py
import os
import pty
import time
import select
import termios
import tty

TEAM_ID = "2026-IN-SPACE-CAN-7USAT-008"

class TeensyMock:
    def __init__(self):
        # Create the virtual serial cables
        self.master, self.slave = pty.openpty()
        self.port_name = os.ttyname(self.slave)
        
        # CRITICAL: Set PTY to 'Raw' mode so Linux doesn't corrupt our \r bytes
        tty.setraw(self.master)
        tty.setraw(self.slave)
        
        self.is_transmitting = False
        self.packet_count = 0
        self.mission_time_sec = 0.0
        self.base_alt = 0.0
        
    def run(self):
        print("==================================================")
        print(f"[TEENSY MOCK] Virtual Port: {self.port_name}")
        print("[TEENSY MOCK] Status: SILENT. Waiting for commands.")
        print("==================================================")
        
        last_tx_time = time.time()
        in_buffer = b""

        try:
            while True:
                # 1. Non-blocking read from GCS (checking for commands every 50ms)
                r, _, _ = select.select([self.master], [], [], 0.05)
                if r:
                    data = os.read(self.master, 1024)
                    if data:
                        in_buffer += data
                        if b'\r' in in_buffer:
                            cmds = in_buffer.split(b'\r')
                            in_buffer = cmds.pop() # Keep remainder in buffer
                            for c in cmds:
                                if c: self.process_command(c.decode('ascii', errors='ignore'))

                # 2. Transmit at 2Hz (every 0.5 seconds)
                current_time = time.time()
                if self.is_transmitting and (current_time - last_tx_time) >= 0.5:
                    self.transmit_telemetry()
                    last_tx_time = current_time
                    
        except KeyboardInterrupt:
            print("\n[TEENSY MOCK] Shutting down.")
            os.close(self.master)
            os.close(self.slave)
            
    def process_command(self, cmd_str):
        print(f"\n[MOCK RX] Received Command: {cmd_str}")
        if "START_TX" in cmd_str:
            self.is_transmitting = True
            print("[MOCK SYSTEM] Transmissions STARTED at 2Hz.")
        elif "ALT_CAL" in cmd_str:
            print("[MOCK SYSTEM] Sensors Calibrated.")
            self.base_alt = 0.0
            
    def transmit_telemetry(self):
        # Simulate a flight profile over time
        t = self.mission_time_sec
        if t < 10: 
            alt = 0.0
            state = 2
        elif t < 40: 
            alt = (t - 10) * 20.0 
            state = 3
        else: 
            alt = max(0.0, 600.0 - ((t - 40) * 15.0))
            state = 5 if alt > 600 else 6
            
        pressure = 101325 - (alt * 12)
        temp = 35.0 - (alt * 0.006)
        voltage = 8.2
        gnss_time = 1700000000 + int(t)
        lat, lon = 26.739, 83.887
        sats = 9
        accel = "0.0;0.0;9.81"
        gyro_spin = 3450
        opt_data = "TEST_OK"

        packet = f"{TEAM_ID},{t:.1f},{self.packet_count},{alt:.1f},{pressure:.0f},{temp:.1f},{voltage:.2f},{gnss_time},{lat:.4f},{lon:.4f},{alt:.1f},{sats},{accel},{gyro_spin},{state},{opt_data}\r"
        
        # Push the bytes out the virtual cable
        os.write(self.master, packet.encode('ascii'))
        
        # Print a clean confirmation to terminal (overwriting the same line)
        print(f"[MOCK TX 2Hz] Packet {self.packet_count} sent... \r", end="")
        
        self.packet_count += 1
        self.mission_time_sec += 0.5 # Increment by 0.5 seconds for 2Hz

if __name__ == "__main__":
    TeensyMock().run()