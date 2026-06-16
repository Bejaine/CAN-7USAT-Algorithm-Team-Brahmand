## GCS Subsystem

### Environment Setup

``` bash
cd gcs
python3 -m venv gcsenv
```

``` bash
source gcsenv/bin/activate
pip install -r requirements.txt
```

### How To Run

Terminal 1
``` bash
source gcsenv/bin/activate
cd gcs/src/
python3 teensy_mock.py
```

Terminal 2
``` bash
source gcsenv/bin/activate
cd gcs/src/
python3 gcs_ui.py
```

Connect to the laptop port, calibrate, and start telemetry