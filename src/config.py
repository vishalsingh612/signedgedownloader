import os
import yaml
from pathlib import Path
from typing import Any, Dict, List

class ConfigError(Exception):
    """Custom exception raised when config loading fails."""
    pass

class AppConfig:
    def __init__(self, config_path: str = "config/config.yaml"):
        # Resolve project root (the directory containing src/ and config/)
        self.project_root = Path(__file__).resolve().parent.parent
        self.config_file = self.project_root / config_path
        
        self._load_dotenv()
        
        if not self.config_file.exists():
            raise ConfigError(f"Configuration file not found at: {self.config_file}")
            
        try:
            with open(self.config_file, "r") as f:
                self._data = yaml.safe_load(f) or {}
        except Exception as e:
            raise ConfigError(f"Failed to parse config.yaml: {e}")
            
        self._load_config()

    def _load_dotenv(self):
        env_file = self.project_root / ".env"
        if env_file.exists():
            try:
                with open(env_file, "r", encoding="utf-8") as f:
                    for line in f:
                        line = line.strip()
                        if not line or line.startswith("#") or "=" not in line:
                            continue
                        key, val = line.split("=", 1)
                        key = key.strip()
                        val = val.strip().strip("'").strip('"')
                        os.environ[key] = val
            except Exception as e:
                # Fallback print if logger isn't initialized yet
                print(f"Warning: Failed to parse .env file: {e}")

    def _load_config(self):
        # Portal config
        portal = self._data.get("portal", {})
        self.portal_url = portal.get("url", "https://signedge.in.panasonic.com/customer/midlandmicrofinltd/login")
        self.portal_playback_url = portal.get("playback_url", "https://signedge.in.panasonic.com/customer/midlandmicrofinltd/report/content-playback")
        self.portal_email = os.environ.get("PORTAL_EMAIL", portal.get("email", ""))
        self.portal_password = os.environ.get("PORTAL_PASSWORD", portal.get("password", ""))

        # Campaign config
        raw_campaign_name = self._data.get("campaign", {}).get("name", "")
        if isinstance(raw_campaign_name, list):
            self.campaign_names = [str(n).strip() for n in raw_campaign_name if n]
            self.campaign_name = ", ".join(self.campaign_names)
        elif isinstance(raw_campaign_name, str):
            self.campaign_names = [n.strip() for n in raw_campaign_name.split(",") if n.strip()]
            self.campaign_name = raw_campaign_name
        else:
            self.campaign_names = []
            self.campaign_name = ""

        # Paths config - resolve to absolute paths relative to project root
        paths = self._data.get("paths", {})
        self.excel_path = self.project_root / paths.get("excel_path", "config/devices.xlsx")
        dl_path = paths.get("download_dir", "downloads")
        if str(dl_path).startswith("~"):
            self.download_dir = Path(dl_path).expanduser()
        elif Path(dl_path).is_absolute():
            self.download_dir = Path(dl_path)
        else:
            self.download_dir = self.project_root / dl_path
            
        self.gdrive_sync_dir = None
        gdrive_path = paths.get("gdrive_sync_dir", "")
        if gdrive_path:
            if str(gdrive_path).startswith("~"):
                self.gdrive_sync_dir = Path(gdrive_path).expanduser()
            elif Path(gdrive_path).is_absolute():
                self.gdrive_sync_dir = Path(gdrive_path)
            else:
                self.gdrive_sync_dir = self.project_root / gdrive_path

        self.browser_profile_dir = self.project_root / paths.get("browser_profile_dir", "browser_profile")
        self.checkpoint_dir = self.project_root / paths.get("checkpoint_dir", "checkpoints")
        self.log_dir = self.project_root / paths.get("log_dir", "logs")
        self.screenshot_dir = self.project_root / paths.get("screenshot_dir", "screenshots")
        self.email_templates_dir = self.project_root / paths.get("email_templates_dir", "templates/emails")

        # Email config
        email = self._data.get("email", {})
        self.smtp_server = email.get("smtp_server", "")
        self.smtp_port = int(email.get("smtp_port", 587))
        self.smtp_username = email.get("smtp_username", "")
        self.smtp_password = os.environ.get("SMTP_PASSWORD", email.get("smtp_password", ""))
        self.email_sender = email.get("sender", email.get("email_sender", ""))
        self.email_recipients: List[str] = email.get("recipients", [])
        self.email_use_tls = bool(email.get("use_tls", True))

        # Scheduler config
        scheduler = self._data.get("scheduler", {})
        self.scheduler_enabled = bool(scheduler.get("enabled", True))
        self.scheduler_run_time = scheduler.get("run_time", "02:00")
        self.scheduler_timezone = scheduler.get("timezone", "Asia/Kolkata")

        # Automation config
        auto = self._data.get("automation", {})
        self.headless = bool(auto.get("headless", False))
        self.timeout_ms = int(auto.get("timeout_ms", 30000))
        self.action_wait_ms = int(auto.get("action_wait_ms", 2000))
        self.retry_count = int(auto.get("retry_count", 3))
        self.check_login_interval_seconds = int(auto.get("check_login_interval_seconds", 5))
        self.download_start_time = auto.get("download_start_time", "08:30")
        self.download_end_time = auto.get("download_end_time", "09:30")

        # Selectors config
        self.selectors: Dict[str, Dict[str, str]] = self._data.get("selectors", {})

        # Ensure directories exist
        for d in [self.download_dir, self.browser_profile_dir, self.checkpoint_dir, self.log_dir, self.screenshot_dir]:
            d.mkdir(parents=True, exist_ok=True)

# Instantiate a single global config instance
config = AppConfig()
