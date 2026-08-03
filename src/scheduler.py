import sys
import subprocess
from apscheduler.schedulers.blocking import BlockingScheduler
from apscheduler.triggers.cron import CronTrigger
from src.config import config
from src.logger import logger

def start_scheduler(job_func):
    """
    Starts the APScheduler blocking scheduler to run the download job daily.
    Launches the job in a new subprocess to support live code updates.
    """
    if not config.scheduler_enabled:
        logger.info("Scheduler is disabled in config. Skipping scheduler loop.")
        return

    # Parse run_time HH:MM
    try:
        hour, minute = map(int, config.scheduler_run_time.split(":"))
    except Exception:
        logger.error(f"Invalid scheduler.run_time format '{config.scheduler_run_time}'. Expected HH:MM. Defaulting to 02:00.")
        hour, minute = 2, 0

    def trigger_job():
        logger.info("Triggering downloader job in a new subprocess to pick up any code updates...")
        try:
            # Run src.main as a subprocess using the current python executable
            subprocess.run([sys.executable, "-m", "src.main", "--now"], check=True)
            logger.info("Subprocess downloader job completed successfully.")
        except subprocess.CalledProcessError as e:
            logger.error(f"Subprocess downloader job failed with exit code {e.returncode}.")
        except Exception as e:
            logger.error(f"Failed to run downloader subprocess: {e}")

    try:
        scheduler = BlockingScheduler(timezone=config.scheduler_timezone)
        
        trigger = CronTrigger(hour=hour, minute=minute)
        
        scheduler.add_job(
            trigger_job,
            trigger=trigger,
            id="daily_downloader_job",
            name="Daily Campaign Screenshot Downloader",
            replace_existing=True
        )
        
        logger.info(f"Scheduler initialized. Job scheduled daily at {config.scheduler_run_time} ({config.scheduler_timezone})")
        logger.info("Scheduler starting. Use Ctrl+C to stop.")
        scheduler.start()
    except (KeyboardInterrupt, SystemExit):
        logger.info("Scheduler stopped manually.")
    except Exception as e:
        logger.error(f"Scheduler encountered an error: {e}")
        raise
