# Validation Test Matrix: Dryer_Buzzer

This document details the functional, boundary, and negative test scenarios used to validate the stability and accuracy of the state tracking script.

### 1. Functional & State Transition Testing
| Test ID | Scenario Description | Input / Trigger | Expected Behavior | Status |
| :--- | :--- | :--- | :--- | :--- |
| **TC-F01** | Happy Path: Full Cycle | `is_vibrating() == True` for > 300s, then `False` for > 120s | State transitions: `IDLE` -> `STARTING` -> `RUNNING` -> `WAITING_TO_STOP` -> `IDLE`. Buzzer triggers for 3s, Telegram push notification is dispatched, log entries verified. | **PASS** |
| **TC-F02** | Short Transient Vibration | `is_vibrating() == True` for only 45 seconds | State moves `IDLE` -> `STARTING` -> reverts to `IDLE`. No logs confirm a cycle, no buzzer or Telegram notification fires. | **PASS** |
| **TC-F03** | Mid-Cycle Drum Pause | `is_vibrating() == False` for 60 seconds while in `RUNNING` state, then returns to `True` | State transitions `RUNNING` -> `WAITING_TO_STOP` -> reverts to `RUNNING`. No end-of-cycle alerts are prematurely triggered. | **PASS** |

### 2. Boundary & Threshold Value Testing
| Test ID | Scenario Description | Value Tested | Expected Behavior | Status |
| :--- | :--- | :--- | :--- | :--- |
| **TC-B01** | Micro-Vibration Threshold | Delta acceleration calculation equals `1.49 m/s²` | `is_vibrating()` returns `False`. Script remains `IDLE`. | **PASS** |
| **TC-B02** | Exact Match Start Delay | State is `STARTING`; elapsed time reaches exactly `300` seconds | State promotes to `RUNNING`. Log registers "Dryer cycle confirmed". | **PASS** |
| **TC-B03** | Exact Match Stop Delay | State is `WAITING_TO_STOP`; elapsed time reaches exactly `120` seconds | FSM registers cycle completion, runs `trigger_buzzer()`. | **PASS** |

### 3. Negative & Error Resilience Testing
| Test ID | Scenario Description | Condition | Expected Behavior | Status |
| :--- | :--- | :--- | :--- | :--- |
| **TC-N01** | Missing Environment Variables | Unset `TELEGRAM_BOT_TOKEN` in terminal environment | Runtime catches `KeyError` on launch, logs error to `dryer.log`, and cleanly crashes out instead of hanging. | **PASS** |
| **TC-N02** | Hardware Disconnect (I2C) | Unplug ADXL345 physical data line prior to initialization | Hardware block catches exception, logs `Failed to initialize hardware`, execution terminates safely. | **PASS** |
| **TC-N03** | Mid-Run Script Interruption | User issues `Ctrl + C` during active loop | `KeyboardInterrupt` caught. Code jumps to `finally` block executing `GPIO.cleanup()`, ensuring safety of Pi pins. | **PASS** |
