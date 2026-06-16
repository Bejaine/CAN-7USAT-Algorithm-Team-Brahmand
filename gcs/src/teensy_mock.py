# src/teensy_mock.py
import os
import pty
import time
import threading

TEAM_ID = "2026-IN-SPACE-CAN-7USAT-XXX"

def generate_telemetry_string(packet_count, mission_time):
    """
    Generates a mock string matching the competition CSV guidelines.
    Adjusting altitude to simulate a climb and fall.
    """
    # Simulating a flight profile (up to 1000m, then down)
    if mission_time < 30: # Pad wait
        alt = 0.0
        state = 2 # LAUNCH_PAD
    elif mission_time < 80: # Ascent
        alt = (mission_time - 30) * 20.0 
        state = 3 # ASCENT
    else: # Descent
        alt = max(0.0, 1000.0 - ((mission_time - 80) * 15.0))
        state = 5 if alt > 600 else 6 # DESCENT -> AEROBREAK_RELEASE
    
    # Static or slightly jittered mock sensor values
    pressure = 101325 - (alt * 12)
    temp = 35.0 - (alt * 0.006)
    voltage = 8.2
    gnss_time = 1700000000 + mission_time
    lat, lon = 26.739, 83.887 # Kushinagar roughly
    sats = 9
    accel = "0.0;0.0;9.81" # Semicolons so we don't break the main CSV commas
    gyro_spin = 3450 # RPM of mechanical gyro
    opt_data = "TEST_OK"

    # Strict formatting ending with carriage return
    packet = f"{TEAM_ID},{mission_time},{packet_count},{alt:.1f},{pressure:.0f},{temp:.1f},{voltage:.2f},{gnss_time},{lat:.4f},{lon:.4f},{alt:.1f},{sats},{accel},{gyro_spin},{state},{opt_data}\r"
    return packet.encode('ascii')

def main():
    # Create the pseudo-terminal
    master, slave = pty.openpty()
    port_name = os.ttyname(slave)
    
    print("==================================================")
    print(f"[TEENSY MOCK] Virtual Serial Port Created: {port_name}")
    print("[TEENSY MOCK] Point your GCS software to this port.")
    print("==================================================")

    packet_count = 0
    mission_time = 0

    try:
        while True:
            # Generate and write the packet to the master side of the PTY
            packet = generate_telemetry_string(packet_count, mission_time)
            os.write(master, packet)
            
            print(f"[MOCK TX] {packet.decode('ascii').strip()}")
            
            packet_count += 1
            mission_time += 1
            
            # Guidelines mandate 1 Hz or faster. Let's do exactly 1 Hz.
            time.sleep(1.0)
            
    except KeyboardInterrupt:
        print("\n[TEENSY MOCK] Shutting down.")
        os.close(master)
        os.close(slave)

if __name__ == "__main__":
    main()