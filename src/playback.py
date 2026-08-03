import pandas as pd
import traceback
from pathlib import Path
from playwright.sync_api import Page
from src.config import config
from src.logger import logger
from src.checkpoint import checkpoint_manager
from src.login import login, is_logged_in
from src.navigation import select_search_filters, navigate_to_content_playback
from src.downloader import download_device_screenshots

def load_devices() -> list:
    """Loads device names from the Excel configuration file."""
    excel_path = config.excel_path
    if not excel_path.exists():
        logger.error(f"Excel devices file not found at: {excel_path}")
        raise FileNotFoundError(f"Excel devices file not found: {excel_path}")
        
    try:
        # Read Excel sheet
        df = pd.read_excel(excel_path)
        
        # Verify required columns
        required_cols = ["Branch Code", "Branch Name", "Device Name"]
        for col in required_cols:
            if col not in df.columns:
                raise ValueError(f"Missing required column '{col}' in Excel file.")
                
        # Drop empty rows and get Device Names
        devices = df["Device Name"].dropna().astype(str).str.strip().unique().tolist()
        # Filter out empty strings
        devices = [d for d in devices if d]
        logger.info(f"Loaded {len(devices)} unique devices from Excel configuration.")
        return devices
    except Exception as e:
        logger.error(f"Failed to read devices Excel file: {e}")
        raise

def process_devices(page: Page, campaign_name: str, date_ddmmyyyy: str) -> dict:
    """
    Loops through all devices, selects them in the dropdown,
    triggers search, and downloads all available screenshots.
    Resumes from checkpoint if available.
    """
    # Load list of devices from Excel
    devices_list = load_devices()
    
    # Load checkpoint
    checkpoint = checkpoint_manager.load(date_ddmmyyyy)
    completed_devices = set(checkpoint.get("completed_devices", []))
    failed_devices = checkpoint.get("failed_devices", {})
    
    remaining_devices = [d for d in devices_list if d not in completed_devices]
    logger.info(f"Devices list: {len(devices_list)} total. {len(remaining_devices)} remaining to process.")

    device_dropdown_sel = config.selectors["playback"]["device_dropdown"]
    search_button_sel = config.selectors["playback"]["search_button"]
    
    total_images_downloaded = 0
    warnings_count = 0

    for idx, device in enumerate(remaining_devices):
        logger.info(f"--- Processing device ({idx+1}/{len(remaining_devices)}): '{device}' ---")
        
        # Check session status before starting each device
        if not is_logged_in(page):
            logger.warning("Session expired or invalid. Triggering pause/login notifier...")
            from src.notifier import notifier
            notifier.send_session_expired()
            
            # Attempt to re-login or pause loop
            login(page)
            # Re-navigate and re-select filters since session restart could reset state
            navigate_to_content_playback(page)
            select_search_filters(page, campaign_name)

        # Set current device in checkpoint
        checkpoint_manager.set_current_device(device)
        downloaded_images = checkpoint.get("downloaded_images", [])

        try:
            # Clear any previous device selection first
            from src.navigation import clear_react_select, select_react_select_option
            clear_react_select(page, device_dropdown_sel)
            
            # Select device from React-Select dropdown
            select_react_select_option(page, device_dropdown_sel, device)
            
            # Click Search button
            logger.info("Clicking Search button...")
            search_btn = page.locator(search_button_sel).first
            search_btn.wait_for(state="visible", timeout=8000)
            search_btn.click(force=True)

            
            # Download screenshots
            downloaded = download_device_screenshots(page, device, downloaded_images)
            total_images_downloaded += downloaded
            
            # Mark completed
            checkpoint_manager.mark_device_completed(device)
            logger.info(f"Device '{device}' processed successfully.")
            
            # Clear dropdown selection at the end of processing this device
            try:
                clear_react_select(page, device_dropdown_sel)
            except Exception:
                pass
                
        except Exception as e:
            err_msg = str(e)
            logger.error(f"Error processing device '{device}': {err_msg}")
            logger.debug(traceback.format_exc())
            
            # Capture failure screenshot
            screenshot_path = config.screenshot_dir / f"fail_device_{device}.png"
            try:
                page.screenshot(path=str(screenshot_path))
                logger.info(f"Error screenshot saved to {screenshot_path}")
            except Exception as se:
                logger.warning(f"Could not save failure screenshot: {se}")

            # Mark as failed in checkpoint and move to next device
            checkpoint_manager.mark_device_failed(device, err_msg)
            warnings_count += 1
            
            # Attempt to reset/navigate back to reports page to restore state for next device
            try:
                navigate_to_content_playback(page)
                select_search_filters(page, campaign_name)
            except Exception as re:
                logger.error(f"Failed to reset/navigate back after device failure: {re}")

    # Reload checkpoint to get final counts
    final_checkpoint = checkpoint_manager.load(date_ddmmyyyy)
    
    return {
        "total_devices": len(devices_list),
        "completed_count": len(final_checkpoint.get("completed_devices", [])),
        "failed_count": len(final_checkpoint.get("failed_devices", {})),
        "images_downloaded": total_images_downloaded,
        "failed_summary": final_checkpoint.get("failed_devices", {}),
        "warnings_count": warnings_count
    }
