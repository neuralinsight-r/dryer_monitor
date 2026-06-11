import time
import logging
import os

import board
import busio
import adafruit_adxl34x
import RPi.GPIO as GPIO

import urllib.request
import urllib.parse
import json

# =========================================================
# --- CONFIGURATION ---
# =========================================================

# Replace Twilio variables with Telegram variables
TELEGRAM_BOT_TOKEN = os.environ['TELEGRAM_BOT_TOKEN']
TELEGRAM_CHAT_ID = os.environ['TELEGRAM_CHAT_ID']

# Pins
BUZZER_PIN = 18  # GPIO 18

# Thresholds
VIBRATION_THRESHOLD = 10
START_DELAY = 300  # 5 minutes
STOP_DELAY = 120   # 2 minutes

# =========================================================
# --- LOGGING SETUP ---
# =========================================================

logging.basicConfig(
    filename='dryer.log',
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)

# =========================================================
# --- INITIALIZATION ---
# =========================================================

try:
    # Set up I2C for the Accelerometer
    i2c = busio.I2C(board.SCL, board.SDA)
    accelerometer = adafruit_adxl34x.ADXL345(i2c)

    # Set up Buzzer
    GPIO.setmode(GPIO.BCM)
    GPIO.setup(BUZZER_PIN, GPIO.OUT)
    GPIO.output(BUZZER_PIN, GPIO.LOW)

    # === TWILIO CLIENT REMOVED FROM HERE ===

    logging.info("System initialized successfully.")

except Exception as e:
    logging.error(f"Failed to initialize hardware: {e}")
    raise

# =========================================================
# --- FUNCTIONS ---
# =========================================================

def send_push(message):
    try:
        url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
        data = urllib.parse.urlencode({
            'chat_id': TELEGRAM_CHAT_ID,
            'text': message
        }).encode('utf-8')
        
        req = urllib.request.Request(url, data=data)
        with urllib.request.urlopen(req) as response:
            if response.status == 200:
                logging.info("Telegram push notification sent successfully.")
            else:
                logging.error(f"Telegram API returned status: {response.status}")

    except Exception as e:
        logging.error(f"Failed to send Telegram notification: {e}")

def trigger_buzzer():
    logging.info("Triggering buzzer.")

    GPIO.output(BUZZER_PIN, GPIO.HIGH)
    time.sleep(3)
    GPIO.output(BUZZER_PIN, GPIO.LOW)

def is_vibrating():
    # Read X, Y, Z acceleration
    x, y, z = accelerometer.acceleration

    # Calculate total acceleration magnitude
    total_accel = (x**2 + y**2 + z**2)**0.5

    # Compare against gravity (~9.8 m/s²)
    return abs(total_accel - 9.8) > VIBRATION_THRESHOLD

# =========================================================
# --- MAIN LOOP ---
# =========================================================

state = "IDLE"
start_time = None
stop_time = None

logging.info("Monitoring started...")

try:
    while True:

        vibrating = is_vibrating()

        if state == "IDLE":

            if vibrating:
                state = "STARTING"
                start_time = time.time()

                logging.info(
                    "Vibration detected. Checking persistence..."
                )

        elif state == "STARTING":

            if not vibrating:
                state = "IDLE"

            elif time.time() - start_time >= START_DELAY:
                state = "RUNNING"

                logging.info(
                    "Dryer cycle confirmed: RUNNING."
                )

        elif state == "RUNNING":

            if not vibrating:
                state = "WAITING_TO_STOP"
                stop_time = time.time()

                logging.info(
                    "Vibration stopped. Confirming cycle end..."
                )

        elif state == "WAITING_TO_STOP":

            if vibrating:
                state = "RUNNING"

                logging.info(
                    "Vibration resumed. Dryer still RUNNING."
                )

            elif time.time() - stop_time >= STOP_DELAY:

                logging.info("Cycle complete!")

                trigger_buzzer()

                send_push(
                    "Laundry is dry! Come get it while it's warm."
                )

                state = "IDLE"

        # Check once per second
        time.sleep(1)

except KeyboardInterrupt:

    logging.info("Program stopped by user.")

finally:

    GPIO.cleanup()
# test deploy beep boop
