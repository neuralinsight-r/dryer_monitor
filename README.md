# Dryer_Buzzer (IoT Appliance State Monitor)

My mom's dryer didn't come with a buzzer nor does it support one as an available option. This is a small passion project to resolve the issue of mom not knowing when the cycle was complete aside from either setting a timer on her phone and/or periodically checking on the dryer. An IoT automation solution deployed on a Raspberry Pi Zeor W (v1) that utilizes an ADXL345 accelerometer to track dryer vibration cycles. It incorporates a time-delayed state machine to prevent false positives and alerts users via a physical GPIO buzzer and SMS notifications via the Twilio API upon cycle completion.

## 🛠️ Engineering & QA Highlights
From a Quality Engineering perspective, this project emphasizes robust error boundaries, security, and edge-case resilience:
* **Finite State Machine (FSM):** Implemented a deterministic state machine (`IDLE` -> `STARTING` -> `RUNNING` -> `WAITING_TO_STOP`) to handle sensor debouncing, filtering out brief transient vibrations or temporary mid-cycle pauses.
* **Production-Grade Logging:** Replaced standard console prints with Python's `logging` library to output timestamped logs (`dryer.log`) with appropriate severity levels (`INFO`, `ERROR`), crucial for real-world debugging and log-parsing automation.
* **Secure Secret Management:** Adheres to security best practices by injecting Twilio API tokens into the runtime via environment variables rather than hardcoding sensitive credentials into version control.
* **Graceful Degradation:** Utilizes `try-except-finally` structures to handle hardware initialization failures and ensures physical GPIO pins are safely released (`GPIO.cleanup()`) if the process is terminated.

---

## 🚀 System Architecture & Setup

### Hardware Component Stack
* Raspberry Pi (configured with BCM GPIO layout)
* ADXL345 Accelerometer (communicating via I2C interface)
* Active Piezo Buzzer (mapped to GPIO Pin 18)

### Installation
1. Clone the repository:
   ```bash
   git clone [https://github.com/neuralinsight-r/Dryer_Buzzer.git](https://github.com/neuralinsight-r/Dryer_Buzzer.git)
   cd Dryer_Buzzer
2. Configure security credentials on your host machine:
   ```bash
   export TWILIO_ACCOUNT_SID='your_actual_sid'
   export TWILIO_AUTH_TOKEN='your_actual_token'
3. Execute the script:
   ```bash
   python3 main.py

## 🧪 Comprehensive QA Test Suite
See [test_cases.md](./test_cases.md) for the complete end-to-end validation matrix covering boundary testing, state transitions, and error injection.
