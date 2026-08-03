import smtplib
import traceback
from datetime import datetime
from email.mime.application import MIMEApplication
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from pathlib import Path
from typing import List, Optional
from jinja2 import Environment, FileSystemLoader
from src.config import config
from src.logger import logger

class EmailNotifier:
    def __init__(self):
        self.templates_dir = config.email_templates_dir
        self.env = Environment(loader=FileSystemLoader(self.templates_dir))

    def _send_email(self, subject: str, html_content: str, attachment_paths: Optional[List[Path]] = None):
        """Sends an HTML email to configured recipients with optional attachments."""
        if not config.smtp_server or not config.smtp_username:
            logger.warning("SMTP email notifications not configured. Skipping sending email.")
            return

        msg = MIMEMultipart()
        msg["From"] = config.email_sender
        msg["To"] = ", ".join(config.email_recipients)
        msg["Subject"] = subject

        # Attach HTML body
        msg.attach(MIMEText(html_content, "html"))

        # Attach optional files
        if attachment_paths:
            for path in attachment_paths:
                if not path.exists():
                    logger.warning(f"Attachment file {path} not found. Skipping.")
                    continue
                try:
                    with open(path, "rb") as f:
                        part = MIMEApplication(f.read(), Name=path.name)
                    part['Content-Disposition'] = f'attachment; filename="{path.name}"'
                    msg.attach(part)
                except Exception as e:
                    logger.error(f"Failed to attach file {path}: {e}")

        try:
            # Connect to SMTP server
            if config.smtp_port == 465:
                # SSL
                server = smtplib.SMTP_SSL(config.smtp_server, config.smtp_port, timeout=30)
            else:
                # STARTTLS or plain
                server = smtplib.SMTP(config.smtp_server, config.smtp_port, timeout=30)
                if config.email_use_tls:
                    server.starttls()
            
            if config.smtp_password:
                server.login(config.smtp_username, config.smtp_password)
                
            server.sendmail(config.email_sender, config.email_recipients, msg.as_string())
            server.quit()
            logger.info(f"Email sent successfully: '{subject}' to {config.email_recipients}")
        except Exception as e:
            logger.error(f"Failed to send email notification: {e}")
            logger.debug(traceback.format_exc())

    def send_started(self, campaign: str, date_str: str, expected_devices_count: int):
        """Sends job started notification."""
        try:
            template = self.env.get_template("started.html")
            html = template.render(
                time=datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                campaign=campaign,
                date=date_str,
                expected_devices_count=expected_devices_count
            )
            self._send_email(f"Panasonic Downloader STARTED - Campaign: {campaign}", html)
        except Exception as e:
            logger.error(f"Failed to render started.html: {e}")

    def send_login_required(self, reason: str):
        """Sends waiting for manual login / reCAPTCHA email."""
        try:
            template = self.env.get_template("waiting_login.html")
            html = template.render(
                portal_url=config.portal_url,
                reason=reason
            )
            self._send_email("ACTION REQUIRED: Panasonic Signedge Login / reCAPTCHA Required", html)
        except Exception as e:
            logger.error(f"Failed to render waiting_login.html: {e}")

    def send_session_expired(self):
        """Sends session expired notification."""
        try:
            template = self.env.get_template("session_expired.html")
            html = template.render(
                portal_url=config.portal_url,
                time=datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            )
            self._send_email("ALERT: Panasonic Signedge Session Expired (Automation Paused)", html)
        except Exception as e:
            logger.error(f"Failed to render session_expired.html: {e}")

    def send_completed(self, campaign: str, date_str: str, duration: str, devices_processed: int, images_downloaded: int, failures_count: int, warnings_count: int, failures_summary: str = ""):
        """Sends completion summary report email."""
        try:
            template = self.env.get_template("completed.html")
            html = template.render(
                campaign=campaign,
                date=date_str,
                duration=duration,
                devices_processed=devices_processed,
                images_downloaded=images_downloaded,
                failures_count=failures_count,
                warnings_count=warnings_count,
                failures_summary=failures_summary
            )
            self._send_email(f"Panasonic Downloader COMPLETED - Campaign: {campaign}", html)
        except Exception as e:
            logger.error(f"Failed to render completed.html: {e}")

    def send_failure(self, reason: str, stacktrace: str, screenshot_path: Optional[Path] = None):
        """Sends critical failure notification."""
        try:
            template = self.env.get_template("failure.html")
            html = template.render(
                time=datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                reason=reason,
                stacktrace=stacktrace
            )
            attachments = []
            if screenshot_path and screenshot_path.exists():
                attachments.append(screenshot_path)
            
            # Also attach errors log if it exists and has content
            err_log = config.log_dir / "errors.log"
            if err_log.exists() and err_log.stat().st_size > 0:
                attachments.append(err_log)
                
            self._send_email("CRITICAL FAILURE: Panasonic Signedge Downloader Crashed", html, attachments)
        except Exception as e:
            logger.error(f"Failed to render failure.html: {e}")

# Instantiate notifier global instance
notifier = EmailNotifier()
