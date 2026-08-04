import os
import json
import re
import csv
import yaml
import threading
import pandas as pd
from datetime import datetime, timedelta
from http.server import ThreadingHTTPServer, HTTPServer, BaseHTTPRequestHandler
from pathlib import Path

# Paths
WORKSPACE_DIR = Path(__file__).resolve().parent.parent
LOG_DIR = WORKSPACE_DIR / "logs"
APP_LOG_PATH = LOG_DIR / "app.log"
DOWNLOADS_CSV_PATH = LOG_DIR / "downloads.csv"
DEVICES_EXCEL_PATH = WORKSPACE_DIR / "config" / "devices.xlsx"
ENV_PATH = WORKSPACE_DIR / ".env"

PORT = int(os.environ.get("PORT", 8000))

# Background manual job runner state
job_running = False
job_status = "idle"

def run_manual_job_thread():
    global job_running, job_status
    job_running = True
    job_status = "running"
    import sys
    import subprocess
    try:
        print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] [MANUAL] Starting manual run...")
        subprocess.run([sys.executable, "-m", "src.main", "--now"], check=True)
        job_status = "completed"
        print("[MANUAL] Manual run completed successfully.")
    except Exception as e:
        job_status = f"failed: {e}"
        print(f"[MANUAL] Manual run failed: {e}")
    finally:
        job_running = False

def read_env_vars():
    env_vars = {"PORTAL_EMAIL": "", "PORTAL_PASSWORD": "", "SMTP_PASSWORD": ""}
    if ENV_PATH.exists():
        try:
            with open(ENV_PATH, "r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if not line or line.startswith("#") or "=" not in line:
                        continue
                    key, val = line.split("=", 1)
                    key = key.strip()
                    val = val.strip().strip("'").strip('"')
                    if key in env_vars:
                        env_vars[key] = val
        except Exception as e:
            print(f"Error reading env file: {e}")
    return env_vars

def write_env_vars(env_vars):
    lines = []
    keys_written = set()
    try:
        if ENV_PATH.exists():
            with open(ENV_PATH, "r", encoding="utf-8") as f:
                for line in f:
                    stripped = line.strip()
                    if stripped and not stripped.startswith("#") and "=" in stripped:
                        key = stripped.split("=", 1)[0].strip()
                        if key in env_vars:
                            lines.append(f"{key}={env_vars[key]}\n")
                            keys_written.add(key)
                            continue
                    lines.append(line)
        
        for key, val in env_vars.items():
            if key not in keys_written:
                lines.append(f"{key}={val}\n")
                
        with open(ENV_PATH, "w", encoding="utf-8") as f:
            f.writelines(lines)
    except Exception as e:
        print(f"Error writing env file: {e}")

def get_stats_data():
    """Parses downloads.csv and app.log to aggregate metrics for the last 30 days."""
    today = datetime.now().date()
    date_list = [today - timedelta(days=i) for i in range(30)]
    date_strings = [d.strftime("%Y-%m-%d") for d in date_list]

    # Initialize stats dict
    stats = {d: {"success": 0, "failed": 0, "skipped": 0, "downloads": [], "log_counts": {"INFO": 0, "WARNING": 0, "ERROR": 0, "CRITICAL": 0}} for d in date_strings}

    total_success = 0
    total_failed = 0
    total_skipped = 0
    durations = []

    # 1. Parse downloads.csv
    if DOWNLOADS_CSV_PATH.exists():
        try:
            with open(DOWNLOADS_CSV_PATH, "r", encoding="utf-8") as f:
                reader = csv.DictReader(f)
                for row in reader:
                    ts_str = row.get("Timestamp", "")
                    if not ts_str:
                        continue
                    try:
                        date_part = ts_str.split(" ")[0]
                    except Exception:
                        continue

                    if date_part in stats:
                        status = row.get("Status", "").upper()
                        duration = 0.0
                        try:
                            duration = float(row.get("Duration", 0.0))
                            durations.append(duration)
                        except ValueError:
                            pass

                        record = {
                            "time": ts_str.split(" ")[1] if " " in ts_str else "",
                            "device": row.get("Device", ""),
                            "filename": row.get("Filename", ""),
                            "status": status,
                            "duration": duration,
                            "remarks": row.get("Remarks", "")
                        }
                        stats[date_part]["downloads"].append(record)

                        if status == "SUCCESS":
                            stats[date_part]["success"] += 1
                            total_success += 1
                        elif status == "SKIPPED":
                            stats[date_part]["skipped"] += 1
                            total_skipped += 1
                        else:
                            stats[date_part]["failed"] += 1
                            total_failed += 1
        except Exception as e:
            print(f"Error reading downloads.csv: {e}")

    # 2. Parse app.log for counts
    if APP_LOG_PATH.exists():
        try:
            log_pattern = re.compile(r"^(\d{4}-\d{2}-\d{2}) \d{2}:\d{2}:\d{2} \[([A-Z]+)\]")
            with open(APP_LOG_PATH, "r", encoding="utf-8", errors="ignore") as f:
                for line in f:
                    m = log_pattern.match(line)
                    if m:
                        date_str, level = m.groups()
                        if date_str in stats:
                            if level in stats[date_str]["log_counts"]:
                                stats[date_str]["log_counts"][level] += 1
        except Exception as e:
            print(f"Error parsing app.log: {e}")

    # Aggregated metrics
    avg_duration = round(sum(durations) / len(durations), 2) if durations else 0.0
    total_records = total_success + total_failed
    success_rate = round((total_success / total_records) * 100, 1) if total_records else 100.0

    # Count configured devices in Excel if possible
    device_count = 0
    if DEVICES_EXCEL_PATH.exists():
        try:
            df = pd.read_excel(DEVICES_EXCEL_PATH)
            device_count = len(df["Device Name"].dropna().unique())
        except Exception:
            pass

    daily_summary = []
    for d in date_strings:
        day_data = stats[d]
        daily_summary.append({
            "date": d,
            "display_date": datetime.strptime(d, "%Y-%m-%d").strftime("%B %d, %Y"),
            "success": day_data["success"],
            "failed": day_data["failed"],
            "skipped": day_data.get("skipped", 0),
            "total_downloads": day_data["success"] + day_data["failed"] + day_data.get("skipped", 0),
            "log_counts": day_data["log_counts"],
            "download_records": day_data["downloads"]
        })

    return {
        "kpis": {
            "total_success": total_success,
            "total_failed": total_failed,
            "success_rate": success_rate,
            "avg_duration_sec": avg_duration,
            "device_count": device_count
        },
        "daily": daily_summary
    }

def get_logs_for_date(target_date_str):
    """Filters logs in app.log for a specific YYYY-MM-DD date."""
    logs = []
    if not APP_LOG_PATH.exists():
        return logs

    try:
        with open(APP_LOG_PATH, "r", encoding="utf-8", errors="ignore") as f:
            for line in f:
                if line.startswith(target_date_str):
                    logs.append(line.rstrip())
    except Exception as e:
        print(f"Error reading app.log for date: {e}")
    return logs

class DashboardHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path == "/":
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.end_headers()
            self.wfile.write(HTML_TEMPLATE.encode("utf-8"))
        elif self.path == "/api/stats":
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            data = get_stats_data()
            self.wfile.write(json.dumps(data).encode("utf-8"))
        elif self.path.startswith("/api/logs?date="):
            date_str = self.path.split("date=")[1].strip()
            # Validate format YYYY-MM-DD
            if re.match(r"^\d{4}-\d{2}-\d{2}$", date_str):
                logs = get_logs_for_date(date_str)
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.end_headers()
                self.wfile.write(json.dumps({"date": date_str, "logs": logs}).encode("utf-8"))
            else:
                self.send_error(400, "Invalid Date format. Use YYYY-MM-DD.")
        elif self.path == "/api/config":
            try:
                config_file = WORKSPACE_DIR / "config" / "config.yaml"
                if config_file.exists():
                    with open(config_file, "r", encoding="utf-8") as f:
                        config_yaml = yaml.safe_load(f) or {}
                else:
                    config_yaml = {}
                
                env_vars = read_env_vars()
                
                portal = config_yaml.get("portal", {})
                campaign = config_yaml.get("campaign", {})
                email = config_yaml.get("email", {})
                scheduler = config_yaml.get("scheduler", {})
                automation = config_yaml.get("automation", {})
                
                res = {
                    "portal_url": portal.get("url", "https://signedge.in.panasonic.com/customer/midlandmicrofinltd/login"),
                    "portal_playback_url": portal.get("playback_url", "https://signedge.in.panasonic.com/customer/midlandmicrofinltd/report/content-playback"),
                    "portal_email": env_vars.get("PORTAL_EMAIL", portal.get("email", "")),
                    "portal_password": env_vars.get("PORTAL_PASSWORD", portal.get("password", "")),
                    "campaign_name": campaign.get("name", ""),
                    "smtp_server": email.get("smtp_server", ""),
                    "smtp_port": email.get("smtp_port", 587),
                    "smtp_username": email.get("smtp_username", ""),
                    "smtp_password": env_vars.get("SMTP_PASSWORD", email.get("smtp_password", "")),
                    "sender": email.get("sender", ""),
                    "recipients": ", ".join(email.get("recipients", [])),
                    "use_tls": email.get("use_tls", True),
                    "scheduler_enabled": scheduler.get("enabled", True),
                    "scheduler_run_time": scheduler.get("run_time", "02:00"),
                    "scheduler_timezone": scheduler.get("timezone", "Asia/Kolkata"),
                    "download_start_time": automation.get("download_start_time", "08:30"),
                    "download_end_time": automation.get("download_end_time", "09:30")
                }
                
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.end_headers()
                self.wfile.write(json.dumps(res).encode("utf-8"))
            except Exception as e:
                self.send_error(500, f"Failed to load config: {e}")
                
        elif self.path == "/api/devices":
            try:
                devices = []
                if DEVICES_EXCEL_PATH.exists():
                    df = pd.read_excel(DEVICES_EXCEL_PATH)
                    for index, row in df.iterrows():
                        devices.append({
                            "branch_code": str(row.get("Branch Code", "")).strip() if pd.notna(row.get("Branch Code")) else "",
                            "branch_name": str(row.get("Branch Name", "")).strip() if pd.notna(row.get("Branch Name")) else "",
                            "device_name": str(row.get("Device Name", "")).strip() if pd.notna(row.get("Device Name")) else ""
                        })
                
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.end_headers()
                self.wfile.write(json.dumps(devices).encode("utf-8"))
            except Exception as e:
                self.send_error(500, f"Failed to load devices: {e}")
        elif self.path == "/api/job-status":
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(json.dumps({"running": job_running, "status": job_status}).encode("utf-8"))
        else:
            self.send_error(404, "Not Found")

    def do_POST(self):
        content_length = int(self.headers['Content-Length'])
        post_data = self.rfile.read(content_length)
        
        if self.path == "/api/config":
            try:
                data = json.loads(post_data.decode("utf-8"))
                config_file = WORKSPACE_DIR / "config" / "config.yaml"
                
                if config_file.exists():
                    with open(config_file, "r", encoding="utf-8") as f:
                        yaml_data = yaml.safe_load(f) or {}
                else:
                    yaml_data = {}
                
                if "portal" not in yaml_data: yaml_data["portal"] = {}
                if "campaign" not in yaml_data: yaml_data["campaign"] = {}
                if "email" not in yaml_data: yaml_data["email"] = {}
                if "scheduler" not in yaml_data: yaml_data["scheduler"] = {}
                if "automation" not in yaml_data: yaml_data["automation"] = {}
                
                yaml_data["portal"]["url"] = data.get("portal_url", "")
                yaml_data["portal"]["playback_url"] = data.get("portal_playback_url", "")
                yaml_data["portal"]["email"] = data.get("portal_email", "")
                yaml_data["portal"]["password"] = data.get("portal_password", "")
                
                yaml_data["campaign"]["name"] = data.get("campaign_name", "")
                
                yaml_data["email"]["smtp_server"] = data.get("smtp_server", "")
                yaml_data["email"]["smtp_port"] = int(data.get("smtp_port", 587))
                yaml_data["email"]["smtp_username"] = data.get("smtp_username", "")
                yaml_data["email"]["smtp_password"] = data.get("smtp_password", "")
                yaml_data["email"]["sender"] = data.get("sender", "")
                
                recips = data.get("recipients", "")
                if recips:
                    yaml_data["email"]["recipients"] = [r.strip() for r in recips.split(",") if r.strip()]
                else:
                    yaml_data["email"]["recipients"] = []
                    
                yaml_data["email"]["use_tls"] = bool(data.get("use_tls", True))
                
                yaml_data["scheduler"]["enabled"] = bool(data.get("scheduler_enabled", True))
                yaml_data["scheduler"]["run_time"] = data.get("scheduler_run_time", "02:00")
                yaml_data["scheduler"]["timezone"] = data.get("scheduler_timezone", "Asia/Kolkata")
                
                yaml_data["automation"]["download_start_time"] = data.get("download_start_time", "08:30")
                yaml_data["automation"]["download_end_time"] = data.get("download_end_time", "09:30")
                
                with open(config_file, "w", encoding="utf-8") as f:
                    yaml.safe_dump(yaml_data, f, default_flow_style=False)
                
                # Update .env
                env_vars = {
                    "PORTAL_EMAIL": data.get("portal_email", ""),
                    "PORTAL_PASSWORD": data.get("portal_password", ""),
                    "SMTP_PASSWORD": data.get("smtp_password", "")
                }
                write_env_vars(env_vars)
                
                # Reload config in memory
                try:
                    from src.config import config as app_config
                    app_config._load_dotenv()
                    with open(config_file, "r") as f:
                        app_config._data = yaml.safe_load(f) or {}
                    app_config._load_config()
                except Exception as ce:
                    print(f"Error reloading config in memory: {ce}")
                
                try:
                    start_background_scheduler()
                except Exception as se:
                    print(f"Error restarting background scheduler: {se}")
                
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.end_headers()
                self.wfile.write(json.dumps({"status": "success", "message": "Settings saved successfully."}).encode("utf-8"))
            except Exception as e:
                self.send_error(500, f"Failed to save settings: {e}")
                
        elif self.path == "/api/devices":
            try:
                payload = json.loads(post_data.decode("utf-8"))
                
                rows = []
                for item in payload:
                    rows.append({
                        "Branch Code": item.get("branch_code", "").strip(),
                        "Branch Name": item.get("branch_name", "").strip(),
                        "Device Name": item.get("device_name", "").strip()
                    })
                
                df = pd.DataFrame(rows)
                df.to_excel(DEVICES_EXCEL_PATH, index=False)
                
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.end_headers()
                self.wfile.write(json.dumps({"status": "success", "message": "Devices inventory Excel file updated."}).encode("utf-8"))
            except Exception as e:
                self.send_error(500, f"Failed to save devices: {e}")
                
        elif self.path == "/api/clean-history":
            try:
                # 1. Clean downloads/
                downloads_dir = WORKSPACE_DIR / "downloads"
                if downloads_dir.exists():
                    import shutil
                    for child in downloads_dir.iterdir():
                        if child.is_dir():
                            shutil.rmtree(child)
                        else:
                            child.unlink()
                
                # 2. Clean checkpoints/
                checkpoints_dir = WORKSPACE_DIR / "checkpoints"
                if checkpoints_dir.exists():
                    for child in checkpoints_dir.iterdir():
                        child.unlink()
                        
                # 3. Truncate logs
                if APP_LOG_PATH.exists():
                    with open(APP_LOG_PATH, "w") as f:
                        f.write("")
                err_log_path = LOG_DIR / "errors.log"
                if err_log_path.exists():
                    with open(err_log_path, "w") as f:
                        f.write("")
                        
                # 4. Reset downloads.csv
                if DOWNLOADS_CSV_PATH.exists():
                    with open(DOWNLOADS_CSV_PATH, "w", newline="", encoding="utf-8") as f:
                        writer = csv.writer(f)
                        writer.writerow(["Timestamp", "Device", "Filename", "Status", "Duration", "Remarks"])
                        
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.end_headers()
                self.wfile.write(json.dumps({"status": "success", "message": "All execution history, checkpoints, and logs have been reset successfully."}).encode("utf-8"))
            except Exception as e:
                self.send_error(500, f"Failed to clean history: {e}")
        elif self.path == "/api/run-now":
            global job_running, job_status
            if job_running:
                self.send_response(400)
                self.send_header("Content-Type", "application/json")
                self.end_headers()
                self.wfile.write(json.dumps({"status": "error", "message": "A downloader job is already running."}).encode("utf-8"))
                return
            
            threading.Thread(target=run_manual_job_thread, daemon=True).start()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(json.dumps({"status": "success", "message": "Manual run triggered successfully."}).encode("utf-8"))
        else:
            self.send_error(404, "Not Found")

    def log_message(self, format, *args):
        # Prevent spamming terminal logs
        pass

# HTML Dashboard Interface Template with dynamic JS logic and premium layout
HTML_TEMPLATE = """<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Panasonic Signedge - Screenshot Downloader Dashboard</title>
    <link href="https://fonts.googleapis.com/css2?family=Outfit:wght@300;400;600;700&display=swap" rel="stylesheet">
    <style>
        :root {
            --bg-primary: #0a0e17;
            --bg-card: rgba(18, 26, 42, 0.7);
            --bg-accent: #1e293b;
            --text-main: #f8fafc;
            --text-muted: #94a3b8;
            --color-success: #10b981;
            --color-danger: #ef4444;
            --color-warn: #f59e0b;
            --color-info: #06b6d4;
            --glow-green: 0 0 15px rgba(16, 185, 129, 0.4);
            --glow-blue: 0 0 15px rgba(6, 182, 212, 0.4);
        }

        * {
            margin: 0;
            padding: 0;
            box-sizing: border-box;
        }

        body {
            font-family: 'Outfit', sans-serif;
            background-color: var(--bg-primary);
            color: var(--text-main);
            min-height: 100vh;
            padding: 2.5rem 1.5rem;
            background-image: radial-gradient(circle at 10% 20%, rgba(30, 41, 59, 0.3) 0%, transparent 40%),
                              radial-gradient(circle at 90% 80%, rgba(6, 182, 212, 0.1) 0%, transparent 40%);
            background-attachment: fixed;
        }

        .container {
            max-width: 1200px;
            margin: 0 auto;
        }

        header {
            display: flex;
            justify-content: space-between;
            align-items: center;
            margin-bottom: 2.5rem;
            border-bottom: 1px solid rgba(255,255,255,0.05);
            padding-bottom: 1.5rem;
        }

        .brand h1 {
            font-size: 1.8rem;
            font-weight: 700;
            letter-spacing: -0.5px;
            background: linear-gradient(to right, #ffffff, #06b6d4);
            -webkit-background-clip: text;
            -webkit-text-fill-color: transparent;
        }

        .brand p {
            font-size: 0.9rem;
            color: var(--text-muted);
            margin-top: 0.2rem;
        }

        .status-badge {
            display: flex;
            align-items: center;
            gap: 0.5rem;
            background: rgba(16, 185, 129, 0.1);
            color: var(--color-success);
            padding: 0.4rem 1rem;
            border-radius: 9999px;
            font-size: 0.85rem;
            font-weight: 600;
            border: 1px solid rgba(16, 185, 129, 0.2);
            box-shadow: var(--glow-green);
        }

        .status-dot {
            width: 8px;
            height: 8px;
            background-color: var(--color-success);
            border-radius: 50%;
            animation: pulse 2s infinite;
        }

        @keyframes pulse {
            0% { transform: scale(0.9); opacity: 0.6; }
            50% { transform: scale(1.2); opacity: 1; }
            100% { transform: scale(0.9); opacity: 0.6; }
        }

        /* Tabs Navigation */
        .tabs-nav {
            display: flex;
            gap: 0.8rem;
            margin-bottom: 2.5rem;
            border-bottom: 1px solid rgba(255, 255, 255, 0.05);
            padding-bottom: 0.5rem;
        }

        .tab-nav-btn {
            background: none;
            border: none;
            color: var(--text-muted);
            font-size: 0.95rem;
            font-weight: 600;
            padding: 0.6rem 1.2rem;
            cursor: pointer;
            border-radius: 8px;
            transition: all 0.3s ease;
        }

        .tab-nav-btn:hover {
            color: var(--text-main);
            background: rgba(255, 255, 255, 0.02);
        }

        .tab-nav-btn.active {
            color: var(--color-info);
            background: rgba(6, 182, 212, 0.1);
            border: 1px solid rgba(6, 182, 212, 0.2);
        }

        /* KPI grid styling */
        .kpi-grid {
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(220px, 1fr));
            gap: 1.5rem;
            margin-bottom: 3rem;
        }

        .kpi-card {
            background: var(--bg-card);
            backdrop-filter: blur(10px);
            border: 1px solid rgba(255, 255, 255, 0.05);
            padding: 1.5rem;
            border-radius: 16px;
            transition: all 0.3s ease;
        }

        .kpi-card:hover {
            transform: translateY(-3px);
            border-color: rgba(6, 182, 212, 0.2);
        }

        .kpi-label {
            font-size: 0.85rem;
            text-transform: uppercase;
            letter-spacing: 1px;
            color: var(--text-muted);
            margin-bottom: 0.5rem;
            font-weight: 600;
        }

        .kpi-value {
            font-size: 2.2rem;
            font-weight: 700;
            color: var(--text-main);
            letter-spacing: -1px;
        }

        .section-title {
            font-size: 1.4rem;
            font-weight: 600;
            margin-bottom: 1.5rem;
            letter-spacing: -0.5px;
        }

        .section-subtitle {
            font-size: 0.9rem;
            color: var(--text-muted);
            margin-top: -1.2rem;
            margin-bottom: 1.8rem;
        }

        /* List Cards */
        .day-card {
            background: var(--bg-card);
            border: 1px solid rgba(255, 255, 255, 0.04);
            border-radius: 14px;
            margin-bottom: 1rem;
            overflow: hidden;
            transition: all 0.3s ease;
        }

        .day-card.active {
            border-color: rgba(6, 182, 212, 0.3);
            box-shadow: 0 10px 30px rgba(0,0,0,0.4);
        }

        .day-header {
            display: flex;
            justify-content: space-between;
            align-items: center;
            padding: 1.2rem 1.5rem;
            cursor: pointer;
            user-select: none;
        }

        .day-header:hover {
            background: rgba(255, 255, 255, 0.01);
        }

        .day-info {
            display: flex;
            align-items: center;
            gap: 1.5rem;
        }

        .day-date {
            font-weight: 600;
            font-size: 1.05rem;
        }

        .day-badge {
            font-size: 0.8rem;
            padding: 0.2rem 0.6rem;
            border-radius: 6px;
            font-weight: 600;
        }

        .day-badge.success {
            background: rgba(16, 185, 129, 0.1);
            color: var(--color-success);
        }

        .day-badge.failed {
            background: rgba(239, 44, 44, 0.1);
            color: var(--color-danger);
        }

        .day-badge.warning {
            background: rgba(245, 158, 11, 0.1);
            color: var(--color-warn);
        }

        .day-toggle-icon {
            color: var(--text-muted);
            transition: transform 0.3s ease;
        }

        .day-card.active .day-toggle-icon {
            transform: rotate(180deg);
        }

        /* Inside day details */
        .day-details {
            display: none;
            border-top: 1px solid rgba(255, 255, 255, 0.05);
            background: rgba(10, 14, 23, 0.5);
            padding: 1.5rem;
        }

        .day-card.active .day-details {
            display: block;
        }

        /* Inner Tabs inside Day view */
        .inner-tabs {
            display: flex;
            gap: 1rem;
            margin-bottom: 1.2rem;
            border-bottom: 1px solid rgba(255, 255, 255, 0.05);
            padding-bottom: 0.4rem;
        }

        .inner-tab-btn {
            background: none;
            border: none;
            color: var(--text-muted);
            cursor: pointer;
            font-size: 0.85rem;
            font-weight: 600;
            padding: 0.4rem 0.8rem;
            border-radius: 4px;
            transition: all 0.2s ease;
        }

        .inner-tab-btn:hover {
            color: var(--text-main);
        }

        .inner-tab-btn.active {
            color: var(--color-info);
            background: rgba(6, 182, 212, 0.05);
        }

        .inner-tab-content {
            display: none;
        }

        .inner-tab-content.active {
            display: block;
        }

        /* Log console */
        .log-console {
            background: #05070c;
            border: 1px solid rgba(255, 255, 255, 0.05);
            font-family: 'Courier New', Courier, monospace;
            padding: 1rem;
            border-radius: 8px;
            max-height: 400px;
            overflow-y: auto;
            font-size: 0.85rem;
            line-height: 1.4;
        }

        .log-line {
            margin-bottom: 0.25rem;
            white-space: pre-wrap;
        }

        .log-line.INFO { color: #a1a1aa; }
        .log-line.WARNING { color: var(--color-warn); }
        .log-line.ERROR { color: var(--color-danger); font-weight: 600; }
        .log-line.CRITICAL { color: #ffffff; background-color: var(--color-danger); font-weight: 700; padding: 0.1rem 0.3rem; border-radius: 3px; }

        /* Tables */
        .table-wrapper {
            overflow-x: auto;
            border: 1px solid rgba(255, 255, 255, 0.05);
            border-radius: 8px;
        }

        table {
            width: 100%;
            border-collapse: collapse;
            text-align: left;
            font-size: 0.9rem;
        }

        th, td {
            padding: 0.9rem 1.2rem;
            border-bottom: 1px solid rgba(255, 255, 255, 0.03);
        }

        th {
            background-color: rgba(255, 255, 255, 0.02);
            font-weight: 600;
            color: var(--text-muted);
            font-size: 0.8rem;
            text-transform: uppercase;
            letter-spacing: 0.5px;
        }

        tr:last-child td {
            border-bottom: none;
        }

        .status-pill {
            display: inline-block;
            font-size: 0.75rem;
            padding: 0.15rem 0.5rem;
            border-radius: 4px;
            font-weight: 600;
        }

        .status-pill.success {
            background-color: rgba(16, 185, 129, 0.1);
            color: var(--color-success);
        }

        .status-pill.failed {
            background-color: rgba(239, 68, 68, 0.1);
            color: var(--color-danger);
        }

        .status-pill.skipped {
            background-color: rgba(245, 158, 11, 0.1);
            color: #f59e0b;
        }

        .no-data {
            text-align: center;
            color: var(--text-muted);
            padding: 3rem;
            font-size: 0.95rem;
        }

        /* Spinner */
        .spinner {
            border: 3px solid rgba(255, 255, 255, 0.03);
            border-top: 3px solid var(--color-info);
            border-radius: 50%;
            width: 40px;
            height: 40px;
            animation: spin 1s linear infinite;
            margin: 4rem auto;
        }

        @keyframes spin {
            0% { transform: rotate(0deg); }
            100% { transform: rotate(360deg); }
        }

        /* Form Controls & Styling */
        .card-large {
            background: var(--bg-card);
            backdrop-filter: blur(10px);
            border: 1px solid rgba(255, 255, 255, 0.05);
            padding: 2rem;
            border-radius: 16px;
            margin-bottom: 2rem;
        }

        .settings-grid {
            display: grid;
            grid-template-columns: 1fr 1fr;
            gap: 2rem;
            margin-bottom: 2rem;
        }

        @media(max-width: 768px) {
            .settings-grid {
                grid-template-columns: 1fr;
            }
        }

        .settings-section {
            background: var(--bg-card);
            border: 1px solid rgba(255, 255, 255, 0.05);
            padding: 1.5rem;
            border-radius: 12px;
            margin-bottom: 1.5rem;
        }

        .settings-section h3 {
            font-size: 1.1rem;
            margin-bottom: 1.2rem;
            border-bottom: 1px solid rgba(255, 255, 255, 0.05);
            padding-bottom: 0.5rem;
            color: var(--color-info);
        }

        .form-group {
            margin-bottom: 1rem;
            display: flex;
            flex-direction: column;
            gap: 0.4rem;
        }

        .form-group label {
            font-size: 0.85rem;
            color: var(--text-muted);
            font-weight: 600;
        }

        .form-group input[type="text"],
        .form-group input[type="password"],
        .form-group input[type="number"] {
            background: rgba(10, 14, 23, 0.8);
            border: 1px solid rgba(255, 255, 255, 0.08);
            border-radius: 8px;
            padding: 0.6rem 0.8rem;
            color: var(--text-main);
            font-family: inherit;
            font-size: 0.95rem;
            transition: all 0.3s ease;
        }

        .form-group input:focus {
            outline: none;
            border-color: var(--color-info);
            box-shadow: 0 0 10px rgba(6, 182, 212, 0.2);
        }

        .form-row {
            display: grid;
            grid-template-columns: 1fr 1fr;
            gap: 1rem;
        }

        .btn {
            padding: 0.65rem 1.5rem;
            border-radius: 8px;
            font-size: 0.95rem;
            font-weight: 600;
            cursor: pointer;
            transition: all 0.3s ease;
            border: none;
            font-family: inherit;
        }

        .btn-primary {
            background: var(--color-info);
            color: #000;
        }

        .btn-primary:hover {
            box-shadow: var(--glow-blue);
            transform: translateY(-1px);
        }

        .btn-secondary {
            background: var(--bg-accent);
            color: var(--text-main);
            border: 1px solid rgba(255, 255, 255, 0.08);
        }

        .btn-secondary:hover {
            background: rgba(255, 255, 255, 0.05);
        }

        .btn-danger {
            background: var(--color-danger);
            color: #fff;
        }

        .btn-danger:hover {
            box-shadow: 0 0 15px rgba(239, 68, 68, 0.4);
            transform: translateY(-1px);
        }

        .danger-zone {
            border: 1px solid rgba(239, 68, 68, 0.2);
            background: rgba(239, 68, 68, 0.03);
            margin-top: 2rem;
        }

        .danger-zone h3 {
            color: var(--color-danger);
            border-bottom: 1px solid rgba(239, 68, 68, 0.1);
        }

        .danger-zone p {
            font-size: 0.9rem;
            color: var(--text-muted);
            margin-bottom: 1rem;
        }

        .form-actions, .table-actions {
            display: flex;
            gap: 1rem;
            justify-content: flex-end;
            margin-top: 1.5rem;
        }

        .toast {
            position: fixed;
            bottom: 2rem;
            right: 2rem;
            padding: 1rem 2rem;
            border-radius: 8px;
            color: white;
            font-weight: 600;
            opacity: 0;
            transform: translateY(10px);
            transition: all 0.3s ease;
            z-index: 999999;
        }

        .toast.show {
            opacity: 1;
            transform: translateY(0);
        }

        .toast-success {
            background-color: var(--color-success);
            box-shadow: 0 4px 15px rgba(16, 185, 129, 0.3);
        }

        .toast-danger {
            background-color: var(--color-danger);
            box-shadow: 0 4px 15px rgba(239, 68, 68, 0.3);
        }

        /* Excel editor styling */
        #devices-table input[type="text"] {
            background: rgba(10, 14, 23, 0.6);
            border: 1px solid rgba(255, 255, 255, 0.05);
            border-radius: 4px;
            padding: 0.4rem 0.6rem;
            color: var(--text-main);
            font-family: inherit;
            font-size: 0.9rem;
        }
        #devices-table input[type="text"]:focus {
            outline: none;
            border-color: var(--color-info);
            background: rgba(10, 14, 23, 0.9);
        }
    </style>
</head>
<body>
    <div class="container">
        <header>
            <div class="brand">
                <h1>Panasonic Signedge Downloader</h1>
                <p>Management & Monitoring Portal</p>
            </div>
            <div style="display: flex; align-items: center; gap: 1rem; flex-wrap: wrap;">
                <button id="run-now-btn" class="btn btn-primary" style="padding: 0.5rem 1rem; font-size: 0.85rem;" onclick="triggerManualRun()">
                    ⚡ Run Downloader Now
                </button>
                <div class="status-badge">
                    <span id="scheduler-status-dot" class="status-dot"></span>
                    <span id="scheduler-status-text">Active Scheduler</span>
                </div>
            </div>
        </header>

        <div class="tabs-nav">
            <button class="tab-nav-btn active" onclick="showDashboardTab('analytics-tab')">Execution Analytics</button>
            <button class="tab-nav-btn" onclick="showDashboardTab('devices-tab')">Device Inventory</button>
            <button class="tab-nav-btn" onclick="showDashboardTab('settings-tab')">System Settings</button>
        </div>

        <!-- 1. Execution Analytics Tab -->
        <div id="analytics-tab" class="tab-content">
            <div class="kpi-grid" id="kpis-container">
                <!-- Loaded dynamically -->
            </div>
            <h2 class="section-title">Daily Execution Logs</h2>
            <div id="daily-summaries-container">
                <!-- Loaded dynamically -->
            </div>
        </div>

        <!-- 2. Device Inventory Tab -->
        <div id="devices-tab" class="tab-content" style="display: none;">
            <h2 class="section-title">Configure Devices (Excel)</h2>
            <p class="section-subtitle">Manage devices list stored in <code>config/devices.xlsx</code>.</p>
            <div class="card-large">
                <div class="table-wrapper">
                    <table id="devices-table">
                        <thead>
                            <tr>
                                <th>Branch Code</th>
                                <th>Branch Name</th>
                                <th>Device Name (Dropdown Value)</th>
                                <th style="width: 80px; text-align: center;">Actions</th>
                            </tr>
                        </thead>
                        <tbody id="devices-table-body">
                            <!-- Dynamically loaded rows -->
                        </tbody>
                    </table>
                </div>
                <div class="table-actions">
                    <button class="btn btn-secondary" onclick="addDeviceRow()">+ Add Row</button>
                    <button class="btn btn-primary" onclick="saveDevices()">Save Devices list</button>
                </div>
            </div>
        </div>

        <!-- 3. System Settings Tab -->
        <div id="settings-tab" class="tab-content" style="display: none;">
            <h2 class="section-title">Global Settings</h2>
            <p class="section-subtitle">Manage configuration parameters, SMTP alerts, and timings.</p>
            
            <form id="settings-form" onsubmit="saveSettings(event)">
                <div class="settings-grid">
                    <!-- Section 1: Portal -->
                    <div class="settings-section">
                        <h3>Panasonic Portal</h3>
                        <div class="form-group">
                            <label>Login URL</label>
                            <input type="text" id="setting_portal_url" required />
                        </div>
                        <div class="form-group">
                            <label>Playback URL</label>
                            <input type="text" id="setting_portal_playback_url" required />
                        </div>
                        <div class="form-group">
                            <label>Portal Email</label>
                            <input type="text" id="setting_portal_email" required />
                        </div>
                        <div class="form-group">
                            <label>Portal Password</label>
                            <input type="password" id="setting_portal_password" required />
                        </div>
                    </div>
                    
                    <!-- Section 2: Timing & Campaign -->
                    <div class="settings-section">
                        <h3>Campaign & Timings</h3>
                        <div class="form-group">
                            <label>Campaign Name</label>
                            <input type="text" id="setting_campaign_name" required />
                        </div>
                        <div class="form-row">
                            <div class="form-group">
                                <label>Filter Start Time(s)</label>
                                <input type="text" id="setting_download_start_time" placeholder="e.g. 08:30 or 08:30, 12:00" required />
                                <small style="display: block; color: var(--text-muted); margin-top: 0.25rem;">
                                    For multiple slots, separate with commas.
                                </small>
                            </div>
                            <div class="form-group">
                                <label>Filter End Time(s)</label>
                                <input type="text" id="setting_download_end_time" placeholder="e.g. 09:30 or 09:30, 13:00" required />
                                <small style="display: block; color: var(--text-muted); margin-top: 0.25rem;">
                                    Must match the order of start times.
                                </small>
                            </div>
                        </div>
                    </div>
                    
                    <!-- Section 3: Scheduler -->
                    <div class="settings-section">
                        <h3>Scheduler</h3>
                        <div class="form-group">
                            <label style="display: flex; align-items: center; gap: 0.5rem; cursor: pointer; margin-top: 0.5rem;">
                                <input type="checkbox" id="setting_scheduler_enabled" /> Enable Daily Scheduler
                            </label>
                        </div>
                        <div class="form-row">
                            <div class="form-group">
                                <label>Daily Run Time</label>
                                <input type="text" id="setting_scheduler_run_time" placeholder="HH:MM" required />
                            </div>
                            <div class="form-group">
                                <label>Timezone</label>
                                <input type="text" id="setting_scheduler_timezone" required />
                            </div>
                        </div>
                    </div>
                    
                    <!-- Section 4: SMTP Alerts -->
                    <div class="settings-section">
                        <h3>SMTP Email Alerts</h3>
                        <div class="form-row">
                            <div class="form-group">
                                <label>SMTP Host</label>
                                <input type="text" id="setting_smtp_server" />
                            </div>
                            <div class="form-group">
                                <label>SMTP Port</label>
                                <input type="number" id="setting_smtp_port" />
                            </div>
                        </div>
                        <div class="form-row">
                            <div class="form-group">
                                <label>SMTP Username (Email)</label>
                                <input type="text" id="setting_smtp_username" />
                            </div>
                            <div class="form-group">
                                <label>SMTP Password / App Password</label>
                                <input type="password" id="setting_smtp_password" />
                                <small style="display: block; color: var(--text-muted); margin-top: 0.25rem; line-height: 1.4;">
                                    For Gmail: Enable 2-Step Verification on Google Account, search for "App Passwords" under Security, generate one, and paste the 16-character code here.
                                </small>
                            </div>
                        </div>
                        <div class="form-group">
                            <label>Sender Address</label>
                            <input type="text" id="setting_sender" />
                        </div>
                        <div class="form-group">
                            <label>Recipients (Comma-separated)</label>
                            <input type="text" id="setting_recipients" placeholder="email1@example.com, email2@example.com" />
                        </div>
                        <div class="form-group">
                            <label style="display: flex; align-items: center; gap: 0.5rem; cursor: pointer;">
                                <input type="checkbox" id="setting_use_tls" /> Use TLS Encryption
                            </label>
                        </div>
                    </div>
                </div>
                
                <div class="form-actions">
                    <button type="submit" class="btn btn-primary">Save Settings</button>
                </div>
            </form>
            
            <!-- Danger Zone -->
            <div class="settings-section danger-zone">
                <h3>Danger Zone</h3>
                <p>Permanently clears the downloaded screenshots directory, deletes JSON checkpoint states, and resets downloads logs. This action is irreversible.</p>
                <button class="btn btn-danger" onclick="cleanHistory()">Clean History & Reset</button>
            </div>
        </div>
    </div>

    <script>
        async function fetchStats() {
            const summariesContainer = document.getElementById('daily-summaries-container');
            const kpisContainer = document.getElementById('kpis-container');
            
            summariesContainer.innerHTML = '<div class="spinner"></div>';
            
            try {
                const response = await fetch('/api/stats');
                const data = await response.json();
                
                // Render KPIs
                kpisContainer.innerHTML = `
                    <div class="kpi-card">
                        <div class="kpi-label">Configured Devices</div>
                        <div class="kpi-value">${data.kpis.device_count}</div>
                    </div>
                    <div class="kpi-card" style="border-bottom: 2px solid var(--color-success);">
                        <div class="kpi-label">Total Downloads</div>
                        <div class="kpi-value">${data.kpis.total_success}</div>
                    </div>
                    <div class="kpi-card" style="border-bottom: 2px solid var(--color-danger);">
                        <div class="kpi-label">Failed Images</div>
                        <div class="kpi-value">${data.kpis.total_failed}</div>
                    </div>
                    <div class="kpi-card" style="border-bottom: 2px solid var(--color-info);">
                        <div class="kpi-label">Success Rate</div>
                        <div class="kpi-value">${data.kpis.success_rate}%</div>
                    </div>
                `;
                
                // Render summaries
                if (!data.daily || data.daily.length === 0) {
                    summariesContainer.innerHTML = '<div class="no-data">No execution records registered.</div>';
                    return;
                }
                
                summariesContainer.innerHTML = data.daily.map(day => {
                    const statusClass = day.failed > 0 ? 'warning' : 'success';
                    const statusText = day.failed > 0 ? `${day.failed} Failure(s)` : 'Success';
                    
                    return `
                        <div class="day-card" id="day-card-${day.date}">
                            <div class="day-header" onclick="toggleDay('${day.date}')">
                                <div class="day-info">
                                    <div class="day-date">${day.display_date}</div>
                                    <div class="day-badge ${statusClass}">${statusText}</div>
                                    <div style="font-size: 0.85rem; color: var(--text-muted);">
                                        Success: <strong>${day.success}</strong> | Failed: <strong>${day.failed}</strong>
                                    </div>
                                </div>
                                <div class="day-toggle-icon">▼</div>
                            </div>
                            
                            <div class="day-details">
                                <div class="inner-tabs">
                                    <button class="inner-tab-btn active" id="tab-btn-dl-${day.date}" onclick="switchTab('${day.date}', 'dl')">Downloads History</button>
                                    <button class="inner-tab-btn" id="tab-btn-logs-${day.date}" onclick="switchTab('${day.date}', 'logs')">System Console Log</button>
                                </div>
                                
                                <div class="inner-tab-content active" id="tab-content-dl-${day.date}">
                                    ${renderDownloadsTable(day.download_records)}
                                </div>
                                
                                <div class="inner-tab-content" id="tab-content-logs-${day.date}">
                                    <div class="log-console" id="log-console-${day.date}">
                                        <div style="color: var(--text-muted);">Loading console log output...</div>
                                    </div>
                                </div>
                            </div>
                        </div>
                    `;
                }).join('');
            } catch (err) {
                summariesContainer.innerHTML = `<div class="no-data" style="color: var(--color-danger)">Failed to synchronize stats: ${err}</div>`;
            }
        }

        function renderDownloadsTable(records) {
            if (!records || records.length === 0) {
                return '<div class="no-data" style="padding: 1.5rem;">No screenshots downloaded on this day.</div>';
            }
            
            const rows = records.map(r => `
                <tr>
                    <td>${r.time}</td>
                    <td><strong>${escapeHtml(r.device)}</strong></td>
                    <td style="font-family: monospace; font-size: 0.8rem;">${escapeHtml(r.filename)}</td>
                    <td>
                        <span class="status-pill ${r.status === 'SUCCESS' ? 'success' : (r.status === 'SKIPPED' ? 'skipped' : 'failed')}">
                            ${r.status}
                        </span>
                    </td>
                    <td>${r.duration}s</td>
                    <td style="font-size: 0.8rem; color: var(--text-muted);">${escapeHtml(r.remarks)}</td>
                </tr>
            `).join('');

            return `
                <div class="table-wrapper">
                    <table>
                        <thead>
                            <tr>
                                <th>Time</th>
                                <th>Device Name</th>
                                <th>Filename</th>
                                <th>Status</th>
                                <th>Duration</th>
                                <th>Remarks</th>
                            </tr>
                        </thead>
                        <tbody>
                            ${rows}
                        </tbody>
                    </table>
                </div>
            `;
        }

        function toggleDay(dateStr) {
            const card = document.getElementById(`day-card-${dateStr}`);
            const isActive = card.classList.contains('active');
            
            // Close all
            document.querySelectorAll('.day-card').forEach(c => c.classList.remove('active'));
            
            if (!isActive) {
                card.classList.add('active');
                loadLogs(dateStr);
            }
        }

        function switchTab(dateStr, tabName) {
            event.stopPropagation();
            
            const tabBtnDl = document.getElementById(`tab-btn-dl-${dateStr}`);
            const tabBtnLogs = document.getElementById(`tab-btn-logs-${dateStr}`);
            const contentDl = document.getElementById(`tab-content-dl-${dateStr}`);
            const contentLogs = document.getElementById(`tab-content-logs-${dateStr}`);

            if (tabName === 'dl') {
                tabBtnDl.classList.add('active');
                tabBtnLogs.classList.remove('active');
                contentDl.classList.add('active');
                contentLogs.classList.remove('active');
            } else {
                tabBtnDl.classList.remove('active');
                tabBtnLogs.classList.add('active');
                contentDl.classList.remove('active');
                contentLogs.classList.add('active');
                loadLogs(dateStr);
            }
        }

        async function loadLogs(dateStr) {
            const consoleDiv = document.getElementById(`log-console-${dateStr}`);
            if (consoleDiv.getAttribute('data-loaded') === 'true') return;

            try {
                const response = await fetch(`/api/logs?date=${dateStr}`);
                const data = await response.json();
                
                if (!data.logs || data.logs.length === 0) {
                    consoleDiv.innerHTML = '<div class="no-data">No system logs registered for this date.</div>';
                } else {
                    consoleDiv.innerHTML = data.logs.map(line => {
                        let level = 'INFO';
                        if (line.includes('[WARNING]')) level = 'WARNING';
                        else if (line.includes('[ERROR]')) level = 'ERROR';
                        else if (line.includes('[CRITICAL]')) level = 'CRITICAL';
                        
                        return `<div class="log-line ${level}">${escapeHtml(line)}</div>`;
                    }).join('');
                }
                consoleDiv.setAttribute('data-loaded', 'true');
            } catch (err) {
                consoleDiv.innerHTML = `<div class="no-data" style="color: var(--color-danger)">Failed to load daily logs: ${err}</div>`;
            }
        }

        function showDashboardTab(tabId) {
            document.querySelectorAll('.tab-content').forEach(el => el.style.display = 'none');
            document.querySelectorAll('.tab-nav-btn').forEach(el => el.classList.remove('active'));
            
            document.getElementById(tabId).style.display = 'block';
            event.currentTarget.classList.add('active');
            
            if (tabId === 'devices-tab') {
                loadDevices();
            } else if (tabId === 'settings-tab') {
                loadSettings();
            }
        }

        let devicesData = [];
        async function loadDevices() {
            const tbody = document.getElementById('devices-table-body');
            tbody.innerHTML = '<tr><td colspan="4" class="no-data">Loading devices list...</td></tr>';
            try {
                const response = await fetch('/api/devices');
                devicesData = await response.json();
                renderDevices();
            } catch (err) {
                tbody.innerHTML = `<tr><td colspan="4" class="no-data" style="color: var(--color-danger)">Failed to load devices: ${err}</td></tr>`;
            }
        }

        function renderDevices() {
            const tbody = document.getElementById('devices-table-body');
            if (devicesData.length === 0) {
                tbody.innerHTML = '<tr><td colspan="4" class="no-data">No devices configured. Add one below.</td></tr>';
                return;
            }
            tbody.innerHTML = devicesData.map((d, index) => `
                <tr data-index="${index}">
                    <td><input type="text" value="${escapeHtml(d.branch_code)}" onchange="updateDeviceField(${index}, 'branch_code', this.value)" style="width: 100%;" /></td>
                    <td><input type="text" value="${escapeHtml(d.branch_name)}" onchange="updateDeviceField(${index}, 'branch_name', this.value)" style="width: 100%;" /></td>
                    <td><input type="text" value="${escapeHtml(d.device_name)}" onchange="updateDeviceField(${index}, 'device_name', this.value)" style="width: 100%;" /></td>
                    <td style="text-align: center;"><button class="btn btn-danger" style="padding: 0.3rem 0.6rem; font-size: 0.8rem;" onclick="deleteDeviceRow(${index})">Delete</button></td>
                </tr>
            `).join('');
        }

        function updateDeviceField(index, field, val) {
            devicesData[index][field] = val;
        }

        function addDeviceRow() {
            devicesData.push({ branch_code: '', branch_name: '', device_name: '' });
            renderDevices();
        }

        function deleteDeviceRow(index) {
            devicesData.splice(index, 1);
            renderDevices();
        }

        async function saveDevices() {
            try {
                const response = await fetch('/api/devices', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify(devicesData)
                });
                const res = await response.json();
                showToast(res.message || 'Devices list saved successfully!', 'success');
            } catch (err) {
                showToast(`Failed to save devices list: ${err}`, 'danger');
            }
        }

        async function loadSettings() {
            try {
                const response = await fetch('/api/config');
                const data = await response.json();
                
                document.getElementById('setting_portal_url').value = data.portal_url || '';
                document.getElementById('setting_portal_playback_url').value = data.portal_playback_url || '';
                document.getElementById('setting_portal_email').value = data.portal_email || '';
                document.getElementById('setting_portal_password').value = data.portal_password || '';
                
                document.getElementById('setting_campaign_name').value = data.campaign_name || '';
                document.getElementById('setting_download_start_time').value = data.download_start_time || '08:30';
                document.getElementById('setting_download_end_time').value = data.download_end_time || '09:30';
                
                document.getElementById('setting_scheduler_enabled').checked = !!data.scheduler_enabled;
                document.getElementById('setting_scheduler_run_time').value = data.scheduler_run_time || '02:00';
                document.getElementById('setting_scheduler_timezone').value = data.scheduler_timezone || 'Asia/Kolkata';
                
                document.getElementById('setting_smtp_server').value = data.smtp_server || '';
                document.getElementById('setting_smtp_port').value = data.smtp_port || 587;
                document.getElementById('setting_smtp_username').value = data.smtp_username || '';
                document.getElementById('setting_smtp_password').value = data.smtp_password || '';
                document.getElementById('setting_sender').value = data.sender || '';
                document.getElementById('setting_recipients').value = data.recipients || '';
                document.getElementById('setting_use_tls').checked = !!data.use_tls;
            } catch (err) {
                showToast(`Failed to load configuration parameters: ${err}`, 'danger');
            }
        }

        async function saveSettings(event) {
            event.preventDefault();
            const data = {
                portal_url: document.getElementById('setting_portal_url').value,
                portal_playback_url: document.getElementById('setting_portal_playback_url').value,
                portal_email: document.getElementById('setting_portal_email').value,
                portal_password: document.getElementById('setting_portal_password').value,
                
                campaign_name: document.getElementById('setting_campaign_name').value,
                download_start_time: document.getElementById('setting_download_start_time').value,
                download_end_time: document.getElementById('setting_download_end_time').value,
                
                scheduler_enabled: document.getElementById('setting_scheduler_enabled').checked,
                scheduler_run_time: document.getElementById('setting_scheduler_run_time').value,
                scheduler_timezone: document.getElementById('setting_scheduler_timezone').value,
                
                smtp_server: document.getElementById('setting_smtp_server').value,
                smtp_port: parseInt(document.getElementById('setting_smtp_port').value),
                smtp_username: document.getElementById('setting_smtp_username').value,
                smtp_password: document.getElementById('setting_smtp_password').value,
                sender: document.getElementById('setting_sender').value,
                recipients: document.getElementById('setting_recipients').value,
                use_tls: document.getElementById('setting_use_tls').checked
            };
            
            try {
                const response = await fetch('/api/config', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify(data)
                });
                const res = await response.json();
                showToast(res.message || 'Configuration saved successfully!', 'success');
            } catch (err) {
                showToast(`Failed to save settings: ${err}`, 'danger');
            }
        }

        async function cleanHistory() {
            if (!confirm('WARNING: Are you absolutely sure you want to clean history? This will delete all downloaded screenshots, checkpoints, and reset logs.')) {
                return;
            }
            try {
                const response = await fetch('/api/clean-history', { method: 'POST' });
                const res = await response.json();
                showToast(res.message || 'History cleaned successfully!', 'success');
                // Reload analytics
                fetchStats();
            } catch (err) {
                showToast(`Failed to clean history: ${err}`, 'danger');
            }
        }

        function showToast(message, type = 'success') {
            const toast = document.createElement('div');
            toast.className = `toast toast-${type}`;
            toast.innerText = message;
            document.body.appendChild(toast);
            setTimeout(() => {
                toast.classList.add('show');
            }, 50);
            setTimeout(() => {
                toast.classList.remove('show');
                setTimeout(() => toast.remove(), 300);
            }, 3000);
        }

        function escapeHtml(text) {
            if (!text) return '';
            return text
                .toString()
                .replace(/&/g, "&amp;")
                .replace(/</g, "&lt;")
                .replace(/>/g, "&gt;")
                .replace(/"/g, "&quot;")
                .replace(/'/g, "&#039;");
        }

        async function triggerManualRun() {
            const btn = document.getElementById('run-now-btn');
            if (btn.disabled) return;
            
            if (!confirm('Are you sure you want to trigger the daily screenshot downloader manually right now?')) {
                return;
            }
            
            btn.disabled = true;
            btn.innerText = '⏳ Triggering...';
            
            try {
                const response = await fetch('/api/run-now', { method: 'POST' });
                const res = await response.json();
                if (res.status === 'success') {
                    showToast('Manual run triggered in the background.', 'success');
                    pollJobStatus();
                } else {
                    showToast(res.message || 'Failed to trigger job.', 'danger');
                    btn.disabled = false;
                    btn.innerText = '⚡ Run Downloader Now';
                }
            } catch (err) {
                showToast(`Error: ${err}`, 'danger');
                btn.disabled = false;
                btn.innerText = '⚡ Run Downloader Now';
            }
        }

        async function pollJobStatus() {
            const btn = document.getElementById('run-now-btn');
            const schedulerDot = document.getElementById('scheduler-status-dot');
            const schedulerText = document.getElementById('scheduler-status-text');
            if (!btn || !schedulerDot || !schedulerText) return;
            
            try {
                const response = await fetch('/api/job-status');
                const data = await response.json();
                
                if (data.running) {
                    btn.disabled = true;
                    btn.innerText = '⏳ Downloader Job Running...';
                    btn.style.background = 'var(--color-warn)';
                    btn.style.color = '#000';
                    
                    schedulerDot.style.backgroundColor = 'var(--color-warn)';
                    schedulerText.innerText = 'Job In Progress';
                    
                    // Poll again in 3 seconds
                    setTimeout(pollJobStatus, 3000);
                } else {
                    btn.disabled = false;
                    btn.innerText = '⚡ Run Downloader Now';
                    btn.style.background = '';
                    btn.style.color = '';
                    
                    schedulerDot.style.backgroundColor = '';
                    schedulerText.innerText = 'Active Scheduler';
                }
            } catch (err) {
                console.error('Error polling job status:', err);
            }
        }

        // Initialize dashboard and poll status
        fetchStats();
        pollJobStatus();
    </script>
</body>
</html>
"""

class SafeHTTPServer(ThreadingHTTPServer):
    def handle_error(self, request, client_address):
        # Ignore common client-closed connection socket exceptions to prevent terminal clutter
        import sys
        exc_type, exc_value, _ = sys.exc_info()
        if exc_type in (ConnectionAbortedError, ConnectionResetError, BrokenPipeError):
            return
        super().handle_error(request, client_address)

global_scheduler = None

def start_background_scheduler():
    global global_scheduler
    
    # Import inside function to avoid circular dependency
    from src.config import config as app_config
    
    # Stop existing scheduler if running
    if global_scheduler and global_scheduler.running:
        try:
            print("[SCHEDULER] Stopping existing background scheduler...")
            global_scheduler.shutdown()
        except Exception as e:
            print(f"[SCHEDULER] Error shutting down scheduler: {e}")
            
    if not app_config.scheduler_enabled:
        print("[SCHEDULER] Scheduler is disabled in configuration.")
        return

    try:
        from apscheduler.schedulers.background import BackgroundScheduler
        from apscheduler.triggers.cron import CronTrigger
        import sys
        import subprocess

        # Parse run_time HH:MM
        try:
            hour, minute = map(int, app_config.scheduler_run_time.split(":"))
        except Exception:
            hour, minute = 2, 0

        def trigger_job():
            print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] [SCHEDULER] Triggering downloader job...")
            try:
                subprocess.run([sys.executable, "-m", "src.main", "--now"], check=True)
                print("[SCHEDULER] Downloader job completed successfully.")
            except Exception as e:
                print(f"[SCHEDULER] Downloader job failed: {e}")

        global_scheduler = BackgroundScheduler(timezone=app_config.scheduler_timezone)
        trigger = CronTrigger(hour=hour, minute=minute)
        global_scheduler.add_job(
            trigger_job,
            trigger=trigger,
            id="daily_downloader_job",
            name="Daily Campaign Screenshot Downloader",
            replace_existing=True
        )
        global_scheduler.start()
        print(f"==================================================================")
        print(f"🚀 Background scheduler is running live!")
        print(f"📅 Daily download scheduled at: {app_config.scheduler_run_time} ({app_config.scheduler_timezone})")
        print(f"==================================================================")
    except Exception as e:
        print(f"[SCHEDULER] Error starting background scheduler: {e}")

def run_server():
    # Start background scheduler
    start_background_scheduler()
    
    server_address = ('', PORT)
    httpd = SafeHTTPServer(server_address, DashboardHandler)
    print(f"==================================================================")
    print(f"🚀 Dashboard is running live on: http://localhost:{PORT}")
    print(f"📌 Accessible from your browser. Press Ctrl+C to terminate.")
    print(f"==================================================================")
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("\nStopping dashboard server...")
        if global_scheduler and global_scheduler.running:
            global_scheduler.shutdown()
        httpd.server_close()

if __name__ == "__main__":
    run_server()
