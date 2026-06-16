# src/gcs_ui.py
import sys
import pyqtgraph as pg
from PyQt5.QtWidgets import (QApplication, QMainWindow, QWidget, QVBoxLayout, 
                             QHBoxLayout, QPushButton, QLabel, QLineEdit, QGroupBox)
from PyQt5.QtCore import QTimer
from telemetry_core import TelemetryEngine

class GCSDashboard(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("IN-SPACE CANSAT 2026 - Ground Control Station")
        self.resize(1000, 700)

        # Initialize the Data Engine (but don't start it yet)
        self.engine = None
        
        # Data arrays for the graph
        self.time_data = []
        self.alt_data = []

        self.init_ui()

        # Set up the UI refresh timer (runs every 50ms)
        self.update_timer = QTimer()
        self.update_timer.timeout.connect(self.poll_queue)

    def init_ui(self):
        # Main Layout
        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        main_layout = QVBoxLayout(central_widget)

        # --- Top Bar: Connection & Commands ---
        top_layout = QHBoxLayout()
        
        self.port_input = QLineEdit("/dev/pts/7") # Default for testing
        self.port_input.setPlaceholderText("Enter Port (e.g., /dev/ttyUSB0)")
        self.port_input.setFixedWidth(200)
        
        self.connect_btn = QPushButton("CONNECT")
        self.connect_btn.clicked.connect(self.toggle_connection)
        
        self.cal_btn = QPushButton("CALIBRATE SENSORS")
        self.cal_btn.clicked.connect(lambda: self.send_cmd("ALT_CAL"))
        self.cal_btn.setEnabled(False)

        self.start_btn = QPushButton("START TELEMETRY")
        self.start_btn.clicked.connect(lambda: self.send_cmd("START_TX"))
        self.start_btn.setEnabled(False)

        top_layout.addWidget(QLabel("Serial Port:"))
        top_layout.addWidget(self.port_input)
        top_layout.addWidget(self.connect_btn)
        top_layout.addStretch()
        top_layout.addWidget(self.cal_btn)
        top_layout.addWidget(self.start_btn)
        
        main_layout.addLayout(top_layout)

        # --- Middle: Data Readouts ---
        data_group = QGroupBox("Live Telemetry")
        data_layout = QHBoxLayout()
        
        self.lbl_time = QLabel("Mission Time: -- s")
        self.lbl_alt = QLabel("Altitude: -- m")
        self.lbl_state = QLabel("Flight State: --")
        
        # Make the text big and easy to read outside in the sun
        font = self.lbl_time.font()
        font.setPointSize(14)
        font.setBold(True)
        for lbl in [self.lbl_time, self.lbl_alt, self.lbl_state]:
            lbl.setFont(font)
            data_layout.addWidget(lbl)
            
        data_group.setLayout(data_layout)
        main_layout.addWidget(data_group)

        # --- Bottom: Real-Time Plotting ---
        # pyqtgraph handles high-speed plotting perfectly
        pg.setConfigOptions(antialias=True)
        self.plot_widget = pg.PlotWidget(title="CANSAT Altitude vs Time")
        self.plot_widget.setLabel('left', 'Altitude', units='m')
        self.plot_widget.setLabel('bottom', 'Time', units='s')
        self.plot_widget.showGrid(x=True, y=True)
        
        # Create a line reference we will update later
        self.alt_curve = self.plot_widget.plot(pen=pg.mkPen('y', width=2))
        
        main_layout.addWidget(self.plot_widget)

    def toggle_connection(self):
        if self.engine and self.engine.is_running:
            # Disconnect
            self.update_timer.stop()
            self.engine.stop_listening()
            self.engine = None
            self.connect_btn.setText("CONNECT")
            self.port_input.setEnabled(True)
            self.cal_btn.setEnabled(False)
            self.start_btn.setEnabled(False)
        else:
            # Connect
            port = self.port_input.text().strip()
            self.engine = TelemetryEngine(port=port)
            if self.engine.connect():
                self.engine.start_listening()
                self.update_timer.start(50) # Poll queue 20 times a second
                self.connect_btn.setText("DISCONNECT")
                self.port_input.setEnabled(False)
                self.cal_btn.setEnabled(True)
                self.start_btn.setEnabled(True)

    def send_cmd(self, cmd_str):
        if self.engine:
            self.engine.send_command(cmd_str)

    def poll_queue(self):
        """Checks the background engine queue for new data and updates the UI."""
        if not self.engine: return
        
        updated = False
        # Drain the queue of all new packets
        while not self.engine.data_queue.empty():
            data = self.engine.data_queue.get()
            
            # Update Text Labels
            self.lbl_time.setText(f"Mission Time: {data['time']:.1f} s")
            self.lbl_alt.setText(f"Altitude: {data['altitude']:.1f} m")
            self.lbl_state.setText(f"Flight State: {data['state']}")
            
            # Append data for the graph
            self.time_data.append(data['time'])
            self.alt_data.append(data['altitude'])
            updated = True
            
        # Only redraw the graph if we actually received new data points
        if updated:
            self.alt_curve.setData(self.time_data, self.alt_data)

if __name__ == '__main__':
    app = QApplication(sys.argv)
    
    # Optional: Force a dark style for better outdoor visibility
    app.setStyle("Fusion")
    
    window = GCSDashboard()
    window.show()
    sys.exit(app.exec_())