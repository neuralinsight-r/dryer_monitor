import time
import logging
import logging.handlers
import os
import re
import threading
import json
from datetime import datetime
from http.server import HTTPServer, BaseHTTPRequestHandler

import board
import busio
import adafruit_adxl34x
import RPi.GPIO as GPIO

import urllib.request
import urllib.parse

# =========================================================
# --- CONFIGURATION ---
# =========================================================

TELEGRAM_BOT_TOKEN = os.environ['TELEGRAM_BOT_TOKEN']
TELEGRAM_CHAT_ID   = os.environ['TELEGRAM_CHAT_ID']

BUZZER_PIN         = 18       # GPIO 18
VIBRATION_THRESHOLD = 0.45
START_DELAY        = 300      # 5 minutes
STOP_DELAY         = 120      # 2 minutes

WATCHDOG_INTERVAL          = 60    # seconds between watchdog checks
STUCK_STARTING_THRESHOLD   = START_DELAY * 3   # 15 min
STUCK_RUNNING_THRESHOLD = 60 * 120  # 120 minutes
STUCK_WAITING_THRESHOLD    = STOP_DELAY  * 5   # 10 min

LOG_PATH           = 'dryer.log'
STATUS_PORT        = 8080

# =========================================================
# --- LOGGING SETUP (with rotation) ---
# =========================================================

handler = logging.handlers.RotatingFileHandler(
    LOG_PATH,
    maxBytes=5 * 1024 * 1024,   # 5 MB per file
    backupCount=3                # dryer.log + 3 backups = 20 MB max
)
handler.setFormatter(logging.Formatter('%(asctime)s - %(levelname)s - %(message)s'))
logging.getLogger().addHandler(handler)
logging.getLogger().setLevel(logging.INFO)

# =========================================================
# --- INITIALIZATION ---
# =========================================================

try:
    i2c          = busio.I2C(board.SCL, board.SDA)
    accelerometer = adafruit_adxl34x.ADXL345(i2c)

    GPIO.setmode(GPIO.BCM)
    GPIO.setup(BUZZER_PIN, GPIO.OUT)
    GPIO.output(BUZZER_PIN, GPIO.LOW)

    logging.info("System initialized successfully.")

except Exception as e:
    logging.error(f"Failed to initialize hardware: {e}")
    raise

# =========================================================
# --- STATE ---
# =========================================================

state            = "IDLE"
start_time       = None
stop_time        = None
script_start_time = time.time()
cycles_completed = 0
last_watchdog    = time.time()

# =========================================================
# --- LOGGING HELPERS ---
# =========================================================

def log_accel(context=""):
    """Log raw accelerometer values alongside any message."""
    x, y, z   = accelerometer.acceleration
    magnitude = (x**2 + y**2 + z**2)**0.5
    delta     = abs(magnitude - 9.8)
    logging.info(
        f"{context} "
        f"[accel: x={x:.2f}, y={y:.2f}, z={z:.2f}, "
        f"magnitude={magnitude:.2f}, delta={delta:.2f}]"
    )

# =========================================================
# --- SELF-TEST ---
# =========================================================

def self_test():
    """
    Run once at startup. Logs a resting baseline and asserts the
    accelerometer is returning plausible values before the main loop starts.
    """
    x, y, z   = accelerometer.acceleration
    magnitude = (x**2 + y**2 + z**2)**0.5
    logging.info(
        f"Self-test baseline "
        f"[accel: x={x:.2f}, y={y:.2f}, z={z:.2f}, magnitude={magnitude:.2f}]"
    )
    assert 8.0 < magnitude < 12.5, (
        f"Self-test FAILED — implausible resting reading: {magnitude:.2f} m/s². "
        f"Check accelerometer wiring."
    )
    logging.info("Self-test passed.")

# =========================================================
# --- FUNCTIONS ---
# =========================================================

def send_push(message):
    try:
        url  = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
        data = urllib.parse.urlencode({
            'chat_id': TELEGRAM_CHAT_ID,
            'text':    message
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
    x, y, z   = accelerometer.acceleration
    magnitude = (x**2 + y**2 + z**2)**0.5
    return abs(magnitude - 9.8) > VIBRATION_THRESHOLD


def watchdog_check():
    """
    Called once per WATCHDOG_INTERVAL. Logs sensor data when the FSM
    appears stuck so remote diagnosis is possible without physical access.
    """
    now = time.time()

    if state == "STARTING" and start_time and (now - start_time) > STUCK_STARTING_THRESHOLD:
        log_accel("WARNING - Stuck in STARTING for 15+ min.")

    if state == "RUNNING" and start_time and (now - start_time) > STUCK_RUNNING_THRESHOLD:
        log_accel("WARNING - Dryer has been RUNNING for 120+ min. Possible sensor issue or unusually long cycle.")
    
    if state == "WAITING_TO_STOP" and stop_time and (now - stop_time) > STUCK_WAITING_THRESHOLD:
        log_accel("WARNING - Stuck in WAITING_TO_STOP for 10+ min.")

# =========================================================
# --- LOG HISTORY PARSER ---
# =========================================================

def get_cycle_history(limit=5):
    """Return the last N cycle-complete timestamps as plain-English strings."""
    if not os.path.exists(LOG_PATH):
        return []

    completed = []
    pattern   = re.compile(r"^(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}).*Cycle complete")

    with open(LOG_PATH, "r") as f:
        for line in f:
            match = pattern.match(line)
            if match:
                try:
                    dt = datetime.strptime(match.group(1), "%Y-%m-%d %H:%M:%S")
                    completed.append(dt.strftime("%B %d at %I:%M %p"))
                except ValueError:
                    continue

    return completed[-limit:]

# =========================================================
# --- FLASK-STYLE STATUS PAGE ---
# =========================================================

def get_current_status():
    """
    Returns (icon_class, color_key, label, description) reflecting both
    the current FSM state and any stuck/anomaly conditions.
    """
    now = time.time()

    if state == "STARTING" and start_time and (now - start_time) > STUCK_STARTING_THRESHOLD:
        return (
            "ti-alert-triangle", "danger",
            "Stuck – sensor issue",
            "Vibration has been detected for over 15 minutes but the cycle "
            "hasn't confirmed. There may be a sensor issue."
        )

    if state == "WAITING_TO_STOP" and stop_time and (now - stop_time) > STUCK_WAITING_THRESHOLD:
        return (
            "ti-alert-triangle", "danger",
            "Stuck – sensor issue",
            "The dryer appeared to stop over 10 minutes ago but the cycle "
            "hasn't ended. There may be a sensor issue."
        )

    return {
        "IDLE": (
            "ti-zzz", "secondary",
            "Idle",
            "The dryer isn't running."
        ),
        "STARTING": (
            "ti-loader", "warning",
            "Starting",
            "Vibration detected — confirming the dryer is on."
        ),
        "RUNNING": (
            "ti-washing-machine", "success",
            "Running",
            "The dryer is running."
        ),
        "WAITING_TO_STOP": (
            "ti-clock-hour-4", "warning",
            "Finishing",
            "Vibration stopped — confirming the cycle has ended."
        ),
    }.get(state, ("ti-question-mark", "secondary", "Unknown", "Status unavailable."))


COLOR_MAP = {
    "success":   ("#e6f4ea", "#2d6a4f", "#1b4332"),
    "warning":   ("#fff8e1", "#b45309", "#7c3a00"),
    "danger":    ("#fde8e8", "#b91c1c", "#7f1d1d"),
    "secondary": ("#f3f4f6", "#4b5563", "#1f2937"),
}


class StatusHandler(BaseHTTPRequestHandler):

    def do_GET(self):
        icon, color_key, label, description = get_current_status()
        history = get_cycle_history()

        bg, text_strong, text_dark = COLOR_MAP[color_key]

        if history:
            rows = "".join(
                f'<li style="padding:10px 0;border-bottom:0.5px solid #e5e7eb;">'
                f'<span style="color:#16a34a;margin-right:8px;">&#10003;</span>'
                f'{entry}</li>'
                for entry in reversed(history)
            )
            history_html = f'<ul style="list-style:none;padding:0;margin:0;">{rows}</ul>'
        else:
            history_html = '<p style="color:#9ca3af;font-size:15px;">No completed cycles recorded yet.</p>'

        page = f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <meta http-equiv="refresh" content="15">
  <title>Dryer Status</title>
  <link rel="stylesheet" href="https://cdn.jsdelivr.net/npm/@tabler/icons-webfont@latest/tabler-icons.min.css">
  <style>
    * {{ box-sizing: border-box; margin: 0; padding: 0; }}
    body {{
      font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
      background: #f9fafb;
      color: #111827;
      padding: 2rem 1rem;
    }}
    .page   {{ max-width: 420px; margin: 0 auto; }}
    .label  {{ font-size: 11px; font-weight: 600; letter-spacing: 0.07em;
               text-transform: uppercase; color: #9ca3af; margin-bottom: 0.75rem; }}
    .card   {{ background: #fff; border: 0.5px solid #e5e7eb;
               border-radius: 12px; padding: 1.5rem 1.25rem; margin-bottom: 1.5rem; }}
    .icon-wrap {{
      width: 56px; height: 56px; border-radius: 50%;
      background: {bg};
      display: flex; align-items: center; justify-content: center;
      margin: 0 auto 1rem; font-size: 24px; color: {text_strong};
    }}
    .status-label {{ font-size: 22px; font-weight: 500;
                     color: {text_dark}; text-align: center; margin-bottom: 6px; }}
    .status-desc  {{ font-size: 15px; color: #6b7280; text-align: center; line-height: 1.5; }}
    .history-card {{ background: #fff; border: 0.5px solid #e5e7eb;
                     border-radius: 12px; padding: 0 1.25rem; margin-bottom: 1.5rem; }}
    .history-card li:last-child {{ border-bottom: none !important; }}
    .history-text {{ font-size: 15px; color: #374151; }}
    .footer {{ text-align: center; font-size: 12px; color: #9ca3af; }}
  </style>
</head>
<body>
  <div class="page">

    <div class="label">Current status</div>
    <div class="card">
      <div class="icon-wrap"><i class="ti {icon}"></i></div>
      <div class="status-label">{label}</div>
      <div class="status-desc">{description}</div>
    </div>

    <div class="label">Last 5 completed cycles</div>
    <div class="history-card" style="padding: 0 1.25rem;">
      {history_html}
    </div>

    <div class="footer">
      Refreshes every 15 seconds &nbsp;·&nbsp; {time.strftime('%I:%M %p')}
    </div>

  </div>
</body>
</html>""".encode()

        self.send_response(200)
        self.send_header("Content-type", "text/html")
        self.end_headers()
        self.wfile.write(page)

    def log_message(self, *args):
        pass   # suppress HTTP access logs from dryer.log


def start_status_server():
    server = HTTPServer(("", STATUS_PORT), StatusHandler)
    logging.info(f"Status page available on port {STATUS_PORT}.")
    server.serve_forever()

# =========================================================
# --- MAIN LOOP ---
# =========================================================

def run_monitor():
    global state, start_time, stop_time, cycles_completed, last_watchdog

    self_test()

    threading.Thread(
        target=start_status_server,
        daemon=True
    ).start()

    logging.info("Monitoring started.")

    try:
        while True:
            vibrating = is_vibrating()

            if state == "IDLE":
                if vibrating:
                    state      = "STARTING"
                    start_time = time.time()
                    log_accel("Vibration detected. Checking persistence...")

            elif state == "STARTING":
                if not vibrating:
                    log_accel("Vibration lost during STARTING — reverting to IDLE.")
                    state = "IDLE"
                elif time.time() - start_time >= START_DELAY:
                    state = "RUNNING"
                    log_accel("Dryer cycle confirmed: RUNNING.")

            elif state == "RUNNING":
                if not vibrating:
                    state     = "WAITING_TO_STOP"
                    stop_time = time.time()
                    log_accel("Vibration stopped. Confirming cycle end...")

            elif state == "WAITING_TO_STOP":
                if vibrating:
                    state = "RUNNING"
                    log_accel("Vibration resumed. Dryer still RUNNING.")
                elif time.time() - stop_time >= STOP_DELAY:
                    cycles_completed += 1
                    logging.info(
                        f"Cycle complete! "
                        f"[total cycles this session: {cycles_completed}]"
                    )
                    trigger_buzzer()
                    send_push("Laundry is dry! Come get it while it's warm.")
                    state = "IDLE"

            # Watchdog: log sensor data if stuck
            if time.time() - last_watchdog >= WATCHDOG_INTERVAL:
                watchdog_check()
                last_watchdog = time.time()

            time.sleep(1)

    except KeyboardInterrupt:
        logging.info("Program stopped by user.")

    finally:
        GPIO.cleanup()


if __name__ == "__main__":
    run_monitor()
