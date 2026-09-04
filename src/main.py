import sys
from pathlib import Path

# Ensure project root is in sys.path
WORKSPACE_DIR = Path(__file__).resolve().parent.parent
if str(WORKSPACE_DIR) not in sys.path:
    sys.path.insert(0, str(WORKSPACE_DIR))

import argparse
import time
import traceback
from datetime import datetime
from src.config import config
from src.logger import logger
from src.browser import browser_manager
from src.login import login
from src.navigation import navigate_to_content_playback, select_search_filters, get_yesterday_dates
from src.playback import process_devices, load_devices
from src.notifier import notifier
from src.checkpoint import checkpoint_manager
from src.scheduler import start_scheduler

def format_duration(seconds: float) -> str:
    """Formats duration in seconds to a human-readable HH:MM:SS format."""
    hours = int(seconds // 3600)
    minutes = int((seconds % 3600) // 60)
    secs = int(seconds % 60)
    parts = []
    if hours > 0:
        parts.append(f"{hours}h")
    if minutes > 0:
        parts.append(f"{minutes}m")
    parts.append(f"{secs}s")
    return " ".join(parts)

def run_downloader_job(force: bool = False):
    """The core daily automation task."""
    today = datetime.now()
    if today.weekday() == 6 and not force:
        logger.info("Today is Sunday. Skipping downloader run according to Sunday exclusion rule.")
        return

    start_time = time.time()
    dates = get_yesterday_dates()
    target_date = dates["ddmmyyyy"]
    display_date = dates["display"]
    
    # Load devices to count expected devices
    try:
        devices_list = load_devices()
        expected_count = len(devices_list)
    except Exception as e:
        logger.critical(f"Aborting execution. Failed to load device list: {e}")
        return

    campaigns = config.campaign_names
    campaigns_str = ", ".join(campaigns) if campaigns else "None"
    logger.info(f"===== Daily Screenshot Downloader Job Started for {display_date} (Campaigns: {campaigns_str}) =====")
    try:
        notifier.send_started(campaigns_str, display_date, expected_count)
    except Exception as ne:
        logger.error(f"Failed to send job started notification email: {ne}")

    if not campaigns:
        logger.warning("No campaign names found in configuration. Exiting.")
        return

    page = None
    try:
        # Start browser context
        page = browser_manager.start()
        
        # Run login phase
        login_success = login(page)
        if not login_success:
            raise Exception("Login failed or browser was closed before user completed manual login.")
            
        overall_results = {
            "completed_count": 0,
            "images_downloaded": 0,
            "failed_count": 0,
            "warnings_count": 0,
            "failed_summary": {}
        }

        for idx, campaign in enumerate(campaigns):
            logger.info(f"===== Processing Campaign ({idx+1}/{len(campaigns)}): '{campaign}' =====")
            
            # Navigate to Playback Reports page
            navigate_to_content_playback(page)
            
            # Select Date & Campaign Filters
            select_search_filters(page, campaign)
            
            # Process device loop
            results = process_devices(page, campaign, target_date)
            
            overall_results["completed_count"] += results["completed_count"]
            overall_results["images_downloaded"] += results["images_downloaded"]
            overall_results["failed_count"] += results["failed_count"]
            overall_results["warnings_count"] += results["warnings_count"]
            
            for dev, err in results["failed_summary"].items():
                overall_results["failed_summary"][f"{campaign} - {dev}"] = err
            
            # If all devices processed successfully for this campaign, clear checkpoint
            if results["failed_count"] == 0:
                logger.info(f"All devices processed successfully for campaign '{campaign}'. Clearing checkpoint state.")
                checkpoint_manager.set_campaign(campaign)
                checkpoint_manager.clear()
            else:
                logger.warning(f"Campaign '{campaign}' completed with {results['failed_count']} failed devices. Checkpoint preserved for retry.")

        # Calculate duration
        duration_str = format_duration(time.time() - start_time)
        
        # Compile failure summary text if any failures occurred
        failures_summary_html = ""
        if overall_results["failed_count"] > 0:
            failures_summary_html = "<ul>"
            for dev, err in overall_results["failed_summary"].items():
                failures_summary_html += f"<li><strong>{dev}</strong>: {err}</li>"
            failures_summary_html += "</ul>"

        # Send completed email
        try:
            notifier.send_completed(
                campaign=campaigns_str,
                date_str=display_date,
                duration=duration_str,
                devices_processed=overall_results["completed_count"],
                images_downloaded=overall_results["images_downloaded"],
                failures_count=overall_results["failed_count"],
                warnings_count=overall_results["warnings_count"],
                failures_summary=failures_summary_html
            )
        except Exception as ne:
            logger.error(f"Failed to send job completed notification email: {ne}")

        # Copy to Google Drive if configured
        if config.gdrive_sync_dir:
            try:
                import shutil
                date_folder_name = datetime.now().strftime("%Y%m%d")
                source_folder = config.download_dir / date_folder_name
                
                if source_folder.exists():
                    dest_folder = config.gdrive_sync_dir / date_folder_name
                    logger.info(f"Syncing downloads to Google Drive: {dest_folder}")
                    
                    if not dest_folder.exists():
                        shutil.copytree(source_folder, dest_folder)
                        logger.info("Successfully copied folder to Google Drive.")
                    else:
                        logger.info("Google Drive destination already exists. Copying new files...")
                        shutil.copytree(source_folder, dest_folder, dirs_exist_ok=True)
                        logger.info("Successfully synced new files to Google Drive.")
            except Exception as ge:
                logger.error(f"Failed to copy files to Google Drive: {ge}")

        logger.info(f"===== Daily Screenshot Downloader Job Finished successfully in {duration_str} =====")

    except Exception as e:
        duration_str = format_duration(time.time() - start_time)
        err_msg = str(e)
        logger.error(f"===== Job Failure: {err_msg} =====")
        stack = traceback.format_exc()
        logger.error(stack)
        
        # Capture error screenshot if browser is open
        screenshot_path = None
        if page and not page.is_closed():
            screenshot_path = config.screenshot_dir / "critical_job_crash.png"
            try:
                page.screenshot(path=str(screenshot_path))
                logger.info(f"Crash screenshot saved to {screenshot_path}")
            except Exception as se:
                logger.warning(f"Could not save crash screenshot: {se}")

            # Inject a banner indicating error and wait for manual intervention
            try:
                page.evaluate("""() => {
                    const div = document.createElement('div');
                    div.style.position = 'fixed';
                    div.style.top = '10px';
                    div.style.left = '50%';
                    div.style.transform = 'translateX(-50%)';
                    div.style.backgroundColor = '#ef4444';
                    div.style.color = 'white';
                    div.style.padding = '15px 30px';
                    div.style.fontSize = '18px';
                    div.style.fontWeight = 'bold';
                    div.style.borderRadius = '8px';
                    div.style.zIndex = '999999';
                    div.style.boxShadow = '0 4px 12px rgba(0,0,0,0.5)';
                    div.innerHTML = '⚠️ AUTOMATION ERROR: Manual Intervention Required! See terminal logs.';
                    document.body.appendChild(div);
                }""")
            except Exception:
                pass
            
            # Send failure / manual intervention email alert
            try:
                notifier.send_failure(err_msg, stack, screenshot_path)
            except Exception as ne:
                logger.error(f"Failed to send job failure notification email: {ne}")
            
            logger.info("CRITICAL ERROR: Automation paused for manual intervention. Resolve the issue or close the browser window to exit...")
            try:
                while not page.is_closed():
                    page.wait_for_timeout(1000)
            except (KeyboardInterrupt, SystemExit):
                logger.info("Interrupted manual pause.")



        
    finally:
        # Stop browser context
        browser_manager.stop()

def main():
    parser = argparse.ArgumentParser(description="Panasonic Signedge Campaign Screenshot Downloader")
    parser.add_argument("--now", action="store_true", help="Run the download job immediately, then exit.")
    parser.add_argument("--schedule", action="store_true", help="Start the daily background scheduler.")
    
    args = parser.parse_args()
    
    if args.now:
        logger.info("Command line flag --now passed. Running job immediately.")
        run_downloader_job(force=True)
    elif args.schedule:
        logger.info("Command line flag --schedule passed. Starting scheduler.")
        start_scheduler(run_downloader_job)
    else:
        # Default behavior: run scheduler if enabled, else run immediately
        if config.scheduler_enabled:
            logger.info("Starting in Scheduler mode (configured in config.yaml).")
            start_scheduler(run_downloader_job)
        else:
            logger.info("Scheduler disabled in config.yaml. Running job immediately.")
            run_downloader_job(force=True)

if __name__ == "__main__":
    main()
