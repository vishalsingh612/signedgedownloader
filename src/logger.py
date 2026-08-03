import logging
import csv
import sys
from datetime import datetime
from pathlib import Path
from src.config import config

# Setup standard logger
logger = logging.getLogger("signedge_downloader")
logger.setLevel(logging.DEBUG)

# Formatters
formatter = logging.Formatter(
    fmt="%(asctime)s [%(levelname)s] (%(filename)s:%(lineno)d) - %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S"
)

# App Log file handler (INFO and above)
app_log_path = config.log_dir / "app.log"
app_handler = logging.FileHandler(app_log_path, encoding="utf-8")
app_handler.setLevel(logging.INFO)
app_handler.setFormatter(formatter)
logger.addHandler(app_handler)

# Error Log file handler (ERROR and above)
error_log_path = config.log_dir / "errors.log"
error_handler = logging.FileHandler(error_log_path, encoding="utf-8")
error_handler.setLevel(logging.ERROR)
error_handler.setFormatter(formatter)
logger.addHandler(error_handler)

# Console handler (INFO and above)
console_handler = logging.StreamHandler(sys.stdout)
console_handler.setLevel(logging.INFO)
console_handler.setFormatter(formatter)
logger.addHandler(console_handler)

def log_download(device: str, filename: str, status: str, duration: float, remarks: str = ""):
    """
    Appends a download record to logs/downloads.csv.
    Columns: Timestamp, Device, Filename, Status, Duration (seconds), Remarks
    """
    csv_path = config.log_dir / "downloads.csv"
    file_exists = csv_path.exists()
    
    headers = ["Timestamp", "Device", "Filename", "Status", "Duration", "Remarks"]
    
    try:
        with open(csv_path, "a", newline="", encoding="utf-8") as f:
            writer = csv.writer(f)
            if not file_exists:
                writer.writerow(headers)
            writer.writerow([
                datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                device,
                filename,
                status,
                f"{duration:.2f}",
                remarks
            ])
    except Exception as e:
        logger.error(f"Failed to write to downloads.csv: {e}")
