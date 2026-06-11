# Validation Test Matrix: Dryer_Monitor

This document details the functional, boundary, and negative test scenarios used to validate the stability and accuracy of the state tracking script.

### 1. Functional & State Transition Testing
| Test ID | Scenario Description | Input / Trigger | Expected Behavior | Status |
| :--- | :--- | :--- | :--- | :--- |
| **TC-F01** | Happy Path: Full Cycle | `is_vibrating() == True` for > 300s, then `False` for > 120s | State transitions: `IDLE` -> `STARTING` -> `RUNNING` -> `WAITING_TO_STOP` -> `IDLE`. Buzzer triggers for 3s, Telegram push notification is dispatched, log entries verified. | **PASS** |
| **TC-F02** | Short Transient Vibration | `is_vibrating() == True` for only 45 seconds | State moves `IDLE` -> `STARTING` -> reverts to `IDLE`. No logs confirm a cycle, no buzzer or Telegram notification fires. | **PASS** |
| **TC-F03** | Mid-Cycle Drum Pause | `is_vibrating() == False` for 60 seconds while in `RUNNING` state, then returns to `True` | State transitions `RUNNING` -> `WAITING_TO_STOP` -> reverts to `RUNNING`. No end-of-cycle alerts are prematurely triggered. | **PASS** |
| **TC-F04** | Cycle Count Increments | Complete a full cycle end-to-end | `cycles_completed` counter increments by 1. Log entry for `Cycle complete!` includes updated session count. | **PENDING** |
| **TC-F05** | Status Page Reflects FSM State | Advance FSM to each of the four states (`IDLE`, `STARTING`, `RUNNING`, `WAITING_TO_STOP`) | HTTP GET to `localhost:8080` returns correct label and description for each state. Page does not return 500 or blank body at any state. | **PENDING** |
| **TC-F06** | Status Page Cycle History | Complete 6 full cycles sequentially | Cycle history section displays the 5 most recent completions only. Oldest entry is dropped. Timestamps are in correct descending order. | **PENDING** |

### 2. Boundary & Threshold Value Testing
| Test ID | Scenario Description | Value Tested | Expected Behavior | Status |
| :--- | :--- | :--- | :--- | :--- |
| **TC-B01** | Micro-Vibration Threshold | Delta acceleration calculation equals `1.49 m/s²` | `is_vibrating()` returns `False`. Script remains `IDLE`. | **PASS** |
| **TC-B02** | Exact Match Start Delay | State is `STARTING`; elapsed time reaches exactly `300` seconds | State promotes to `RUNNING`. Log registers "Dryer cycle confirmed". | **PASS** |
| **TC-B03** | Exact Match Stop Delay | State is `WAITING_TO_STOP`; elapsed time reaches exactly `120` seconds | FSM registers cycle completion, runs `trigger_buzzer()`. | **PASS** |
| **TC-B04** | Stuck-Starting Threshold Boundary | State is `STARTING`; elapsed time reaches exactly `900` seconds (`START_DELAY * 3`) | Watchdog logs `WARNING - Stuck in STARTING` with raw accelerometer values. No state change occurs — watchdog observes only, does not modify FSM. | **PENDING** |
| **TC-B05** | Stuck-Waiting Threshold Boundary | State is `WAITING_TO_STOP`; elapsed time reaches exactly `600` seconds (`STOP_DELAY * 5`) | Watchdog logs `WARNING - Stuck in WAITING_TO_STOP` with raw accelerometer values. No state change occurs. | **PENDING** |
| **TC-B06** | Stuck State Reflected on Status Page | FSM has been in `STARTING` for > 900 seconds | HTTP GET to `localhost:8080` returns label `Stuck – sensor issue` and danger styling. Normal `Starting` label is no longer shown. | **PENDING** |
| **TC-B07** | Self-Test Lower Boundary | Accelerometer resting magnitude equals `8.01 m/s²` | Self-test passes. Log records baseline reading. Monitoring loop starts normally. | **PENDING** |
| **TC-B08** | Self-Test Upper Boundary | Accelerometer resting magnitude equals `11.49 m/s²` | Self-test passes. Log records baseline reading. Monitoring loop starts normally. | **PENDING** |

### 3. Negative & Error Resilience Testing
| Test ID | Scenario Description | Condition | Expected Behavior | Status |
| :--- | :--- | :--- | :--- | :--- |
| **TC-N01** | Missing Environment Variables | Unset `TELEGRAM_BOT_TOKEN` in terminal environment | Runtime catches `KeyError` on launch, logs error to `dryer.log`, and cleanly crashes out instead of hanging. | **PASS** |
| **TC-N02** | Hardware Disconnect (I2C) | Unplug ADXL345 physical data line prior to initialization | Hardware block catches exception, logs `Failed to initialize hardware`, execution terminates safely. | **PASS** |
| **TC-N03** | Mid-Run Script Interruption | User issues `Ctrl + C` during active loop | `KeyboardInterrupt` caught. Code jumps to `finally` block executing `GPIO.cleanup()`, ensuring safety of Pi pins. | **PASS** |
| **TC-N04** | Self-Test Failure — Low Reading | Accelerometer returns magnitude of `7.99 m/s²` at startup | `self_test()` raises `AssertionError` with descriptive message referencing the reading. Script does not enter monitoring loop. Log records failure. | **PENDING** |
| **TC-N05** | Self-Test Failure — High Reading | Accelerometer returns magnitude of `11.51 m/s²` at startup | `self_test()` raises `AssertionError` with descriptive message. Script does not enter monitoring loop. Log records failure. | **PENDING** |
| **TC-N06** | Self-Test Failure — Zero Reading | Accelerometer returns `(0.0, 0.0, 0.0)` at startup (simulates dead sensor) | `self_test()` raises `AssertionError`. Script terminates before entering monitoring loop. Log records `magnitude=0.00`. | **PENDING** |
| **TC-N07** | Watchdog Does Not Fire Before Threshold | State is `STARTING`; elapsed time is `899` seconds | No `WARNING` log entry is written. FSM remains in `STARTING` without watchdog interference. | **PENDING** |
| **TC-N08** | Network Failure During Push Notification | `urllib.request.urlopen` raises `OSError` during `send_push()` | Exception is caught and logged as `ERROR`. FSM transitions to `IDLE` normally. Script does not crash or hang. | **PENDING** |
| **TC-N09** | Log File Absent at Status Page Load | `dryer.log` does not exist when the status page is requested | Cycle history section renders `No completed cycles recorded yet.` without raising an exception. Current status section is unaffected. | **PENDING** |
| **TC-N10** | Log Rotation Under High Volume | Script is run continuously; log file is artificially grown past `5 MB` | `RotatingFileHandler` creates `dryer.log.1` and continues writing to a fresh `dryer.log`. Total log storage does not exceed 20 MB across all rotated files. | **PENDING** |

### 4. Observability & Logging Verification
| Test ID | Scenario Description | Input / Trigger | Expected Behavior | Status |
| :--- | :--- | :--- | :--- | :--- |
| **TC-O01** | Accelerometer Values Logged on Transition | Trigger any FSM state change | Log entry for the transition includes `x=`, `y=`, `z=`, `magnitude=`, and `delta=` fields with two decimal precision. | **PENDING** |
| **TC-O02** | Startup Baseline Logged | Launch script with healthy accelerometer connected | `dryer.log` contains a `Self-test baseline` entry before the first `Monitoring started` entry. Values reflect actual resting sensor output. | **PENDING** |
| **TC-O03** | Watchdog Sensor Dump While Stuck | FSM stuck in `STARTING` past threshold; wait two `WATCHDOG_INTERVAL` cycles | At least two separate `WARNING - Stuck in STARTING` entries appear in the log, each with current sensor readings. Confirms watchdog fires repeatedly, not just once. | **PENDING** |
| **TC-O04** | Cycle Count in Completion Log | Complete two full cycles in one session | Each `Cycle complete!` log entry includes `total cycles this session` count. First completion reads `1`, second reads `2`. | **PENDING** |
