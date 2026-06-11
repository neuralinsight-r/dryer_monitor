# dryer_monitor (IoT Appliance State Monitor)

My mom's dryer didn't come with a buzzer nor does it support one as an available option. This started out as a small passion project to resolve the issue of mom not knowing when the cycle was complete aside from either setting a timer on her phone and/or periodically checking on the dryer. This is an IoT automation solution deployed on a Raspberry Pi Zero W (v1) that utilizes an ADXL345 accelerometer to track dryer vibration cycles. It incorporates a time-delayed state machine to prevent false positives and alerts users via a physical GPIO buzzer and ~~SMS notifications via the Twilio API~~ Telegram push notification bot upon cycle completion. *A2P 10DLC registration made SMS notifications via Twilio out of scope at this stage hence the pivot to push notifications.* The solution also includes a lightweight HTTP status page accessible via any browser on the local network, displaying the current cycle state in plain English alongside a history of the last 5 completed cycles — designed with non-technical users in mind. Structured logging with automatic log rotation records raw accelerometer readings on every state transition, enabling remote diagnosis of sensor or hardware issues without requiring physical access to the device.

## 🛠️ Engineering & QA Highlights

From a Quality Engineering perspective, this project emphasizes robust error boundaries, security, and edge-case resilience:

* **Finite State Machine (FSM):** Implemented a deterministic state machine (`IDLE` -> `STARTING` -> `RUNNING` -> `WAITING_TO_STOP`) to handle sensor debouncing, filtering out brief transient vibrations or temporary mid-cycle pauses.
* **Production-Grade Logging:** Replaced standard console prints with Python's `logging` library to output timestamped logs (`dryer.log`) with appropriate severity levels (`INFO`, `WARNING`, `ERROR`), crucial for real-world debugging and log-parsing automation. Every state transition includes raw accelerometer values (`x`, `y`, `z`, `magnitude`, `delta`) to support remote diagnosis without physical access to the device.
* **Log Rotation:** Uses `RotatingFileHandler` to cap log storage at 20 MB total (5 MB × 4 files), protecting the SD card from unbounded write growth regardless of runtime duration.
* **Startup Self-Test:** On launch, the script reads a resting accelerometer baseline and asserts the magnitude falls within a plausible gravity range (8.0–11.5 m/s²). An implausible reading crashes cleanly with a descriptive error rather than silently entering a broken monitoring loop.
* **Watchdog Monitoring:** A background check fires every 60 seconds. If the FSM has been stuck in `STARTING` for more than 15 minutes or in `WAITING_TO_STOP` for more than 10 minutes, the watchdog logs a `WARNING` entry with full sensor readings to aid diagnosis of sensor drift, loose wiring, or I2C faults.
* **Secure Secret Management:** Adheres to security best practices by injecting API tokens into the runtime via environment variables rather than hardcoding sensitive credentials into version control.
* **Graceful Degradation:** Utilizes `try-except-finally` structures to handle hardware initialization failures and ensures physical GPIO pins are safely released (`GPIO.cleanup()`) if the process is terminated.

---

## 🚀 System Architecture & Setup

### Hardware Component Stack

* Raspberry Pi Zero W (configured with BCM GPIO layout)
* ADXL345 Accelerometer (communicating via I2C interface)
* Active Piezo Buzzer (mapped to GPIO Pin 18)

### Installation

1. Clone the repository:
   ```bash
   git clone https://github.com/neuralinsight-r/dryer_monitor.git
   cd dryer_monitor
   ```

2. Configure security credentials on your host machine:
   ```bash
   export TELEGRAM_BOT_TOKEN='your_actual_bot_token'
   export TELEGRAM_CHAT_ID='your_actual_chat_id'
   ```

3. Execute the script:
   ```bash
   python3 dryer_monitor.py
   ```

### Remote Access via Tailscale

The Pi is deployed headlessly at a remote location. [Tailscale](https://tailscale.com) is used to maintain SSH access without port forwarding or router configuration on the host network.

```bash
# Install on the Pi
curl -fsSL https://tailscale.com/install.sh | sh
sudo tailscale up
```

Once connected, SSH via the Pi's stable Tailscale IP from any network:
```bash
ssh pi@100.x.x.x
```

Local network SSH continues to work normally via the Pi's local IP when on the same network — Tailscale does not interfere with existing connectivity.

---

## 📊 Status Page

A lightweight HTTP status page runs on port `8080` as a background thread alongside the main monitoring loop. It is accessible from any browser on the same network (or via Tailscale remotely):

```
http://<pi-ip>:8080
```

The page displays two sections:

**Current status** — plain-English description of the FSM state, including anomaly detection. Stuck states (FSM stalled in `STARTING` or `WAITING_TO_STOP` beyond their expected thresholds) surface as a distinct error state with a plain explanation rather than a raw state name.

**Last 5 completed cycles** — parsed from `dryer.log`, showing timestamps of the most recent cycle completions in a human-readable format. Useful for confirming the system has been operating reliably over time.

The page auto-refreshes every 15 seconds. No interaction or technical knowledge is required to read it.

| FSM state | Status page label | Indicator |
| :--- | :--- | :--- |
| `IDLE` | Idle | 🔵 |
| `STARTING` | Starting | 🟡 |
| `RUNNING` | Running | 🟢 |
| `WAITING_TO_STOP` | Finishing | 🟠 |
| Stuck in `STARTING` > 15 min | Stuck – sensor issue | 🔴 |
| Stuck in `WAITING_TO_STOP` > 10 min | Stuck – sensor issue | 🔴 |

---

## 🔍 Diagnosing Issues Remotely

When a stuck or anomalous state is reported, SSH into the Pi and inspect `dryer.log`. Every state transition and watchdog check includes raw sensor values:

```
2026-06-10 14:01:00 - INFO - Vibration detected. Checking persistence... [accel: x=0.12, y=0.03, z=9.81, magnitude=9.81, delta=0.01]
2026-06-10 14:16:00 - WARNING - Stuck in STARTING for 15+ min. [accel: x=14.22, y=0.01, z=0.00, magnitude=14.22, delta=4.42]
```

Common patterns:

| Log observation | Likely cause |
| :--- | :--- |
| `delta` consistently near 0, never exceeds threshold | Sensor physically disconnected from vibration source |
| `magnitude` at or near `0.00` on all axes | I2C/power failure — sensor not responding |
| `magnitude` wildly inconsistent between ticks | Loose wire causing electrical noise |
| `delta` consistently just above threshold at rest | Sensor drift — `VIBRATION_THRESHOLD` may need recalibration |

The startup self-test log line provides a resting baseline to compare against during diagnosis:
```
2026-06-10 09:00:01 - INFO - Self-test baseline [accel: x=0.04, y=-0.01, z=9.79, magnitude=9.79]
2026-06-10 09:00:01 - INFO - Self-test passed.
```

---

## 🧪 Comprehensive QA Test Suite

See [test_cases.md](./test_cases.md) for the complete end-to-end validation matrix covering boundary testing, state transitions, and error injection.

A pytest suite is also available in `test_dryer_buzzer.py`. All hardware dependencies are mocked, so the suite runs on any machine without a Raspberry Pi attached:

```bash
pip install pytest
pytest test_dryer_monitor.py -v
```

The suite covers all cases in the validation matrix including full happy-path cycle simulation, boundary values for `START_DELAY` and `STOP_DELAY`, short transient vibration handling, mid-cycle drum pauses, missing environment variables, hardware initialization failures, and `GPIO.cleanup()` on interrupt.
