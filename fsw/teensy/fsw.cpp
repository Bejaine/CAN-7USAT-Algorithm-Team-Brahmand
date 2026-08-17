#include <Arduino.h>
#include <Wire.h>
#include <TinyGPS++.h>
#include <EEPROM.h>
#include <Adafruit_Sensor.h>
#include <Adafruit_BME280.h>
#include <Adafruit_BNO055.h>
// #include <mavlink.h> // Need to include MAVLink v2 C library

// --- STATE MACHINE ENUMS ---
enum FlightState {
    BOOT = 0,
    TEST_MODE = 1,
    LAUNCH_PAD = 2,
    ASCENT = 3,
    ROCKET_DEPLOY = 4,   // Parachute release
    DESCENT = 5,         // Drone Deploy (<600m)
    AEROBRAKE_RELEASE = 6,
    IMPACT = 7
};

FlightState currentState = BOOT;
int eepromStateAddress = 0; // Where we save state for 30G brownout recovery

// --- HARDWARE OBJECTS ---
Adafruit_BME280 bme;
Adafruit_BNO055 bno = Adafruit_BNO055(55, 0x28);
TinyGPSPlus gps;

// --- NON-BLOCKING TIMERS ---
elapsedMillis timeSinceLastTelemetry;
elapsedMillis timeSinceLastFSMCheck;
elapsedMillis timeSinceLastSensorRead;

// --- GLOBAL VARIABLES ---
float currentAltitude = 0.0;
float baselineAltitude = 0.0;
volatile int gyroPulseCount = 0; // For Hall Effect RPM
int consecutive600mReads = 0;    // Anti-noise buffer

// --- INTERRUPT FOR MECHANICAL GYRO ---
void countGyroPulse() {
    gyroPulseCount++;
}

// --- HELPER: SAVE STATE TO EEPROM ---
void changeState(FlightState newState) {
    if (currentState != newState) {
        currentState = newState;
        EEPROM.write(eepromStateAddress, (uint8_t)currentState);
        // Need to add code here to log state change to SD card
    }
}

void setup() {
    Serial.begin(115200);       // Debug USB
    Serial1.begin(115200);      // XBee Telemetry
    Serial2.begin(115200);      // GPS
    Serial3.begin(115200);      // MAVLink to SpeedyBee

    // 1. Brownout Recovery Check
    uint8_t savedState = EEPROM.read(eepromStateAddress);
    if (savedState > BOOT && savedState <= IMPACT) {
        currentState = (FlightState)savedState;
    } else {
        currentState = LAUNCH_PAD;
        EEPROM.write(eepromStateAddress, (uint8_t)currentState);
    }

    // 2. I2C Timeout Setup (for preventing EMI Freezing)
    Wire.begin();
    Wire.setClock(100000); 
    Wire.setTimeout(10000); // 10ms timeout on I2C bus

    // 3. Initialize Sensors
    if (!bme.begin(0x76)) { /* Handle Error */ }
    if (!bno.begin()) { /* Handle Error */ }

    // 4. Attach RPM Interrupt
    pinMode(2, INPUT_PULLUP);
    attachInterrupt(digitalPinToInterrupt(2), countGyroPulse, RISING);
}

void loop() {
    // ---------------------------------------------------------
    // 1. ASYNCHRONOUS GPS PARSING (Runs as fast as possible)
    // ---------------------------------------------------------
    while (Serial2.available() > 0) {
        gps.encode(Serial2.read());
    }

    // ---------------------------------------------------------
    // 2. SENSOR READING LOOP (100 Hz / Every 10ms)
    // ---------------------------------------------------------
    if (timeSinceLastSensorRead >= 10) {
        timeSinceLastSensorRead = 0;
        
        currentAltitude = bme.readAltitude(1013.25) - baselineAltitude; // Relative Alt
        // Should read BNO055 data here
    }

    // ---------------------------------------------------------
    // 3. FSM EVALUATOR & TRIGGERS (50 Hz / Every 20ms)
    // ---------------------------------------------------------
    if (timeSinceLastFSMCheck >= 20) {
        timeSinceLastFSMCheck = 0;

        switch (currentState) {
            case LAUNCH_PAD:
                // Wait for GCS command to set baseline altitude or detect launch
                if (currentAltitude > 20.0) changeState(ASCENT);
                break;

            case ASCENT:
                // If altitude drops by 10m from peak, we are falling
                // Logic to transition to ROCKET_DEPLOY
                break;

            case ROCKET_DEPLOY:
                // We are falling on the initial parachute. Waiting for 600m.
                if (currentAltitude <= 600.0) {
                    consecutive600mReads++;
                    if (consecutive600mReads >= 5) { // Confirmation Buffer (prevents sensor noise premature deployment)
                        deployDrone();
                        changeState(DESCENT);
                    }
                } else {
                    consecutive600mReads = 0;
                }
                break;

            case DESCENT:
                // Drone is flying autonomously via Ardupilot. Monitor for landing.
                if (currentAltitude < 2.0 /* AND ACCEL IS STABLE */) {
                    changeState(IMPACT);
                }
                break;
                
            case IMPACT:
                // Turn on Audio Beacon
                break;
        }
    }

    // ---------------------------------------------------------
    // 4. TELEMETRY & LOGGING (1 Hz)
    // ---------------------------------------------------------
    if (timeSinceLastTelemetry >= 1000) { // 1 Hz
        timeSinceLastTelemetry = 0;
        
        // Calculate RPM from Interrupt
        int rpm = (gyroPulseCount * 60); // Assuming 1 pulse per sec = 60 RPM
        gyroPulseCount = 0; // Reset for next second

        // Format CSV String
        String telemetry = "1100," + String(millis()/1000) + "," + String(currentState) + "," + String(currentAltitude) /* Need to add all data */;
        
        Serial1.println(telemetry); // Send to XBee
        // Write to SD Card (potentially using the SdFat library)
    }
}

// --- DRONE DEPLOYMENT FUNCTION ---
void deployDrone() {
    // 1. Fire Servo to release parachute/cut away
    // 2. Send MAVLink commands to SpeedyBee over Serial3
    
    /* 
       Pseudocode for MAVLink:
       mavlink_message_t msg;
       uint8_t buf[MAVLINK_MAX_PACKET_LEN];

       // Command 1: ARM Motors
       mavlink_msg_command_long_pack(system_id, component_id, &msg, target_sys, target_comp, MAV_CMD_COMPONENT_ARM_DISARM, 0, 1, 0, 0, 0, 0, 0, 0);
       uint16_t len = mavlink_msg_to_send_buffer(buf, &msg);
       Serial3.write(buf, len);

       delay(50); // Small wait for processing

       // Command 2: SET MODE AUTO (Executes pre-loaded Waypoint)
       // Package and send MAV_CMD_DO_SET_MODE
    */
}