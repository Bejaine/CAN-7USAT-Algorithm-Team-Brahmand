import sys
import pyqtgraph as pg
from PyQt5.QtWidgets import (QApplication, QMainWindow, QWidget, QVBoxLayout, 
                             QHBoxLayout, QPushButton, QLabel, QLineEdit, 
                             QGroupBox, QGridLayout, QScrollArea, QSplitter)
from PyQt5.QtCore import QTimer, Qt
from PyQt5.QtGui import QFont, QColor
from telemetry_core import TelemetryEngine
from PyQt5.QtWidgets import QTextEdit
from PyQt5.QtCore import pyqtSignal, QObject

# Dictionary that maps integers to explicit flight states
FLIGHT_STATES = {
    0: "BOOT", 1: "TEST_MODE", 2: "LAUNCH_PAD", 3: "ASCENT",
    4: "ROCKET_DEPLOY", 5: "DESCENT", 6: "AEROBREAK_RELEASE", 7: "IMPACT"
}

class ConsoleStream(QObject):
    """Intercepts standard terminal output and routes it to a Qt Signal."""
    textWritten = pyqtSignal(str)

    def write(self, text):
        self.textWritten.emit(str(text))

    def flush(self):
        pass

class GCSDashboard(QMainWindow):

    def __init__(self):
        super().__init__()
        self.setWindowTitle("INSPACe CANSAT 2026 | Team Brahmand | Ground Control System")
        self.resize(1300, 700)
        self.is_dark_mode = False

        self.engine = None

        # State tracking for disconnect/reconnect persistence
        self.session_rx = 0
        self.session_loss = 0
        self.session_tx_expected = None

        self.data = {
            'time': [], 'alt': [], 'press': [], 'temp': [], 'volt': [],
            'gyro': [], 'accel': [], 'lat': [], 'lon': [], 'gnss_alt': []
        }

        self.init_ui()

        self.update_timer = QTimer()
        self.update_timer.timeout.connect(self.poll_queue)
        
        # Start in Light Mode per Guidelines
        self.apply_theme()

        # Route terminal output to our UI
        sys.stdout = ConsoleStream()
        sys.stdout.textWritten.connect(self.update_console)
        sys.stderr = sys.stdout # Route errors too

    # User Interface of the GCS
    def init_ui(self):
        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        main_layout = QVBoxLayout(central_widget)

        # ---------------------------------------------------------
        # 1. TOP COMMAND DECK
        # ---------------------------------------------------------
        top_layout = QHBoxLayout()
        
        self.port_input = QLineEdit("/dev/pts/7")
        self.port_input.setPlaceholderText("Port...")
        self.port_input.setFixedWidth(150)
        
        self.connect_btn = QPushButton("CONNECT")
        self.connect_btn.clicked.connect(self.toggle_connection) # When connect_btn is clicked, it runs self.toggle_connection
        
        self.cal_btn = QPushButton("CALIBRATE")
        self.cal_btn.clicked.connect(lambda: self.send_cmd("ALT_CAL"))
        self.cal_btn.setEnabled(False)

        self.start_btn = QPushButton("START TELEMETRY")
        self.start_btn.clicked.connect(lambda: self.send_cmd("START_TX"))
        self.start_btn.setEnabled(False)
        
        self.scale_btn = QPushButton("AUTO-SCALE GRAPHS")
        self.scale_btn.clicked.connect(self.autoscale_graphs)
        
        self.theme_btn = QPushButton("☀️ LIGHT MODE")
        self.theme_btn.clicked.connect(self.toggle_theme)

        # Style Top Deck Buttons
        for btn in [self.connect_btn, self.cal_btn, self.start_btn, self.scale_btn, self.theme_btn]:
            btn.setMinimumHeight(40)
            btn.setFont(QFont("Segoe UI", 11, QFont.Bold))

        top_layout.addWidget(self.port_input)
        top_layout.addWidget(self.connect_btn)
        top_layout.addWidget(self.cal_btn)
        top_layout.addWidget(self.start_btn)
        top_layout.addStretch()
        top_layout.addWidget(self.scale_btn)
        top_layout.addWidget(self.theme_btn)
        
        main_layout.addLayout(top_layout)

        # ---------------------------------------------------------
        # SPACIOUS READOUT DECK
        # ---------------------------------------------------------
        self.readout_group = QGroupBox("Mission Status")
        self.readout_group.setFont(QFont("Segoe UI", 12, QFont.Bold))
        readout_layout = QGridLayout()
        readout_layout.setSpacing(5) # Spacing between rows on the readout deck
        
        # Create Readout Labels
        label_font = QFont("Segoe UI", 14, QFont.Bold)
        self.labels = {
            "team": QLabel("TEAM: --"),
            "time": QLabel("TIME: -- s"),
            "state": QLabel("STATE: --"),
            "sats": QLabel("SATS: --"),
            "tx_cnt": QLabel("TX COUNT: --"),
            "rx_cnt": QLabel("RX COUNT: --"),
            "loss": QLabel("PACKET LOSS: 0"),
            "gnss_time": QLabel("GNSS TIME: --")
        }
        
        for lbl in self.labels.values():
            lbl.setFont(label_font)
            lbl.setAlignment(Qt.AlignCenter)

        # Critical Mission Data
        readout_layout.addWidget(self.labels["team"], 0, 0)
        readout_layout.addWidget(self.labels["time"], 0, 1)
        readout_layout.addWidget(self.labels["state"], 0, 2)
        readout_layout.addWidget(self.labels["sats"], 0, 3)
        
        # Network Health Data
        readout_layout.addWidget(self.labels["tx_cnt"], 1, 0)
        readout_layout.addWidget(self.labels["rx_cnt"], 1, 1)
        readout_layout.addWidget(self.labels["loss"], 1, 2)
        readout_layout.addWidget(self.labels["gnss_time"], 1, 3)
        
        self.readout_group.setLayout(readout_layout)
        main_layout.addWidget(self.readout_group)

        # ---------------------------------------------------------
        # MISSION LOG & COMMAND CONSOLE
        # ---------------------------------------------------------
        console_group = QGroupBox("Mission Console")
        console_layout = QVBoxLayout()
        
        # The scrolling log display
        self.console_log = QTextEdit() # defining the multi line console log text box
        self.console_log.setReadOnly(True)
        self.console_log.setMaximumHeight(300)
        self.console_log.setFont(QFont("Courier", 10, QFont.Bold))
        self.console_log.setStyleSheet("background-color: white; color: #000000;")
        
        # The command input line
        self.cmd_input = QLineEdit() # defining the single line input box
        self.cmd_input.setPlaceholderText("Enter command...")
        self.cmd_input.returnPressed.connect(self.send_custom_command)
        self.cmd_input.setFont(QFont("Courier", 11, QFont.Bold))
        
        console_layout.addWidget(self.console_log)
        console_layout.addWidget(self.cmd_input)
        console_group.setLayout(console_layout)
        
        # main_layout.addWidget(console_group)

        # ---------------------------------------------------------
        # SCROLLABLE GRAPHING GRID
        # ---------------------------------------------------------
        scroll_area = QScrollArea()
        scroll_area.setWidgetResizable(True)

        self.splitter = QSplitter(Qt.Vertical)
        self.splitter.addWidget(console_group)
        self.splitter.addWidget(scroll_area)
        
        scroll_widget = QWidget()
        grid_layout = QGridLayout(scroll_widget)
        grid_layout.setSpacing(15)
        
        # Initialize Plots
        pg.setConfigOptions(antialias=True)
        self.plots = {}
        self.curves = {}
        
        plot_configs = [
            ("alt", "Altitude", "Time (s)", "Altitude (m)"),
            ("press", "Barometric Pressure", "Time (s)", "Pressure (Pa)"),
            ("temp", "Temperature", "Time (s)", "Temp (°C)"),
            ("volt", "Battery Voltage", "Time (s)", "Voltage (V)"),
            ("gyro", "Gyro Spin Rate", "Time (s)", "Rate (deg/s)"),
            ("accel", "Z-Axis Acceleration", "Time (s)", "Accel (m/s²)"),
            ("gnss_alt", "GNSS Altitude", "Time (s)", "GNSS Alt (m)"),
            ("lat", "GNSS Latitude", "Time (s)", "Latitude (°)"),
            ("lon", "GNSS Longitude", "Time (s)", "Longitude (°)"),
            ("map", "GNSS Map", "Longitude", "Latitude")
        ]

        row, col = 0, 0
        for key, title, xlabel, ylabel in plot_configs:
            p = pg.PlotWidget(title=title)

            p.custom_title = title

            p.setLabel('bottom', xlabel)
            p.setLabel('left', ylabel)
            p.showGrid(x=True, y=True)
            p.setMinimumHeight(350) 
            
            if key == "map":
                c = p.plot(pen=None, symbol='o', symbolSize=6, symbolBrush='b')
            else:
                c = p.plot(pen=pg.mkPen('b', width=2.5))
                
            self.plots[key] = p
            self.curves[key] = c
            # p is the widget (the square box with axes). c is the actual line drawn inside it.
            # We save c into self.curves because that is what we update with new data later.
            
            grid_layout.addWidget(p, row, col)
            col += 1
            if col > 1: # 2 Columns
                col = 0
                row += 1

        scroll_area.setWidget(scroll_widget)
        # main_layout.addWidget(scroll_area)
        
        self.splitter.setSizes([200, 600])
        
        main_layout.addWidget(self.splitter)

    # ---------------------------------------------------------
    # UI ACTIONS
    # ---------------------------------------------------------
    def toggle_theme(self):
        self.is_dark_mode = not self.is_dark_mode
        self.apply_theme()

    def apply_theme(self):
        """Swaps the UI color palette without disrupting data"""
        if self.is_dark_mode:
            bg_color = QColor(30, 30, 30)
            text_color = QColor(255, 255, 255)
            graph_bg = 'k'
            graph_fg = 'w'
            line_color = 'y'
            console_bg = "#000000"
            console_fg = "#FFFF00" # Yellow text for dark mode
            self.theme_btn.setText("☾ DARK MODE")
        else: # Light Mode
            bg_color = QColor(240, 240, 240)
            text_color = QColor(0, 0, 0)
            graph_bg = 'w'
            graph_fg = 'k'
            line_color = 'b'
            console_bg = "#FFFFFF"
            console_fg = "#000000" # Black text for light mode
            self.theme_btn.setText("☀️ LIGHT MODE")

        # Apply to main window
        self.setStyleSheet(f"QMainWindow {{ background-color: {bg_color.name()}; }} "
                           f"QLabel, QGroupBox {{ color: {text_color.name()}; }}")
        
        self.console_log.setStyleSheet(f"background-color: {console_bg}; color: {console_fg};")
        self.cmd_input.setStyleSheet(f"background-color: {console_bg}; color: {console_fg};")

        # Apply to pyqtgraph widgets
        for key, p in self.plots.items():
            p.setBackground(graph_bg)
            p.getAxis('bottom').setPen(graph_fg)
            p.getAxis('left').setPen(graph_fg)
            p.getAxis('bottom').setTextPen(graph_fg)
            p.getAxis('left').setTextPen(graph_fg)
            p.setTitle(p.custom_title, color=graph_fg)
            
            # Update line colors (except for the map scatter plot)
            if key == "map":
                self.curves[key].setSymbolBrush(line_color)
            else:
                self.curves[key].setPen(pg.mkPen(line_color, width=2.5))

    def autoscale_graphs(self):
        """Auto scales all graphs to fit to the currently received data"""
        for p in self.plots.values():
            p.enableAutoRange()

    def toggle_connection(self):
        if self.engine and self.engine.is_running:
            self.update_timer.stop()
            self.engine.stop_listening()
            self.engine = None
            self.connect_btn.setText("CONNECT")
            self.port_input.setEnabled(True)
            self.cal_btn.setEnabled(False)
            self.start_btn.setEnabled(False)
        else:
            port = self.port_input.text().strip()
            # Pass historical data to the new engine instance
            self.engine = TelemetryEngine(
                port=port, 
                initial_rx=self.session_rx, 
                initial_loss=self.session_loss, 
                expected_tx=self.session_tx_expected
            )
            if self.engine.connect():
                self.engine.start_listening()
                self.update_timer.start(50) 
                self.connect_btn.setText("DISCONNECT")
                self.port_input.setEnabled(False)
                self.cal_btn.setEnabled(True)
                self.start_btn.setEnabled(True)

    def send_cmd(self, cmd_str):
        if self.engine:
            self.engine.send_command(cmd_str)

    def update_console(self, text):
        """Appends intercepted print() statements to the UI console."""
        cursor = self.console_log.textCursor()
        cursor.movePosition(cursor.End)
        cursor.insertText(text)
        self.console_log.setTextCursor(cursor)
        self.console_log.ensureCursorVisible()

    def send_custom_command(self):
        """Grabs the command from the input line and sends it to the CanSat"""
        cmd = self.cmd_input.text().strip()
        if cmd:
            print(f">> INPUT: {cmd}") # Console echo
            self.send_cmd(cmd)
            self.cmd_input.clear()

    # ---------------------------------------------------------
    # DATA PROCESSING & PLOTTING
    # ---------------------------------------------------------
    def poll_queue(self):
        if not self.engine: return
        
        updated = False
        while not self.engine.data_queue.empty():
            d = self.engine.data_queue.get()

            self.session_rx = d['rx_count']
            self.session_loss = d['lost_count']
            self.session_tx_expected = d['tx_count'] + 1
            
            # Update Readout Deck
            state_str = FLIGHT_STATES.get(d['state'], "UNKNOWN")
            
            self.labels["team"].setText(f"TEAM: {d['team_id']}")
            self.labels["time"].setText(f"TIME: {d['time']:.2f} s")
            self.labels["state"].setText(f"STATE: {state_str}")
            self.labels["sats"].setText(f"SATS: {d['sats']}")
            self.labels["tx_cnt"].setText(f"TX COUNT: {d['tx_count']}")
            self.labels["rx_cnt"].setText(f"RX COUNT: {d['rx_count']}")
            self.labels["gnss_time"].setText(f"GNSS TIME: {d['gnss_time']}")
            
            # Red alert if packets are dropping
            loss = d['lost_count']
            if loss > 0:
                self.labels["loss"].setStyleSheet("color: red;")
            self.labels["loss"].setText(f"PACKET LOSS: {loss}")
            
            # Append to lists
            self.data['time'].append(d['time'])
            self.data['alt'].append(d['altitude'])
            self.data['press'].append(d['pressure'])
            self.data['temp'].append(d['temp'])
            self.data['volt'].append(d['voltage'])
            self.data['gyro'].append(d['gyro_spin'])
            self.data['accel'].append(d['accel_z'])
            self.data['gnss_alt'].append(d['gnss_alt'])
            self.data['lat'].append(d['gnss_lat'])
            self.data['lon'].append(d['gnss_lon'])
            
            updated = True
            
        if updated:
            # Batch update all curves for performance
            t = self.data['time']
            self.curves['alt'].setData(t, self.data['alt'])
            self.curves['press'].setData(t, self.data['press'])
            self.curves['temp'].setData(t, self.data['temp'])
            self.curves['volt'].setData(t, self.data['volt'])
            self.curves['gyro'].setData(t, self.data['gyro'])
            self.curves['accel'].setData(t, self.data['accel'])
            self.curves['gnss_alt'].setData(t, self.data['gnss_alt'])
            self.curves['lat'].setData(t, self.data['lat'])
            self.curves['lon'].setData(t, self.data['lon'])
            
            # The Map takes Lon as X, Lat as Y
            self.curves['map'].setData(self.data['lon'], self.data['lat'])

if __name__ == '__main__':
    app = QApplication(sys.argv)
    window = GCSDashboard()
    window.show()
    sys.exit(app.exec_())