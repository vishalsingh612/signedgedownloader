import re
import time
import traceback
from pathlib import Path
from datetime import time as datetime_time
from datetime import datetime
from playwright.sync_api import Page
from src.config import config
from src.logger import logger, log_download
from src.checkpoint import checkpoint_manager

def _sanitize_folder_name(name: str) -> str:
    """Makes a string safe to use as a folder name on all OSes."""
    name = name.strip().rstrip(",").strip()
    # Replace characters illegal in Windows/macOS folder names
    name = re.sub(r'[<>:"/\\|?*]', "_", name)
    return name or "unknown_device"

def _close_modal(page: Page):
    """Closes the SnapShots modal if it's open."""
    close_sel = config.selectors["download"]["modal_close"]
    try:
        close_btn = page.locator(close_sel).first
        if close_btn.is_visible(timeout=2000):
            close_btn.click()
            page.wait_for_timeout(600)
    except Exception:
        # Try pressing Escape
        try:
            page.keyboard.press("Escape")
            page.wait_for_timeout(600)
        except Exception:
            pass

def _download_from_modal(page: Page, device_folder: Path, device_name: str, row_index: int) -> int:
    """
    After the SnapShots modal is open, clicks each individual 'Download' button
    and saves each file. Returns the number of files successfully downloaded.
    Falls back to 'Download All' if individual buttons can't be found.
    """
    modal_sel = config.selectors["download"]["modal_container"]
    dl_btn_sel = config.selectors["download"]["modal_download_btn"]

    # Wait for modal to fully render
    try:
        page.wait_for_selector(modal_sel, timeout=10000)
        page.wait_for_timeout(800)
    except Exception:
        logger.warning(f"SnapShots modal did not appear for row {row_index + 1}.")
        return 0

    # Find all individual 'Download' buttons in the modal
    # Filter out the 'Download All' button (it contains more text)
    modal = page.locator(modal_sel).first
    all_btns = modal.locator(dl_btn_sel)
    btn_count = all_btns.count()

    # Collect only buttons whose exact text is "Download" (not "Download All")
    download_btn_indices = []
    for i in range(btn_count):
        btn_text = all_btns.nth(i).inner_text().strip()
        if btn_text == "Download":
            download_btn_indices.append(i)

    if not download_btn_indices:
        logger.warning(f"No individual 'Download' buttons in modal for row {row_index + 1}. Trying 'Download All'...")
        return _download_all_from_modal(page, device_folder, device_name, row_index)

    logger.info(f"Row {row_index + 1}: {len(download_btn_indices)} image(s) in SnapShots modal.")
    device_folder.mkdir(parents=True, exist_ok=True)

    downloaded = 0
    safe_device_name = _sanitize_folder_name(device_name)
    current_time_str = datetime.now().strftime("%H%M")
    
    for btn_idx, modal_btn_index in enumerate(download_btn_indices):
        start_time = time.time()
        try:
            btn = modal.locator(dl_btn_sel).nth(modal_btn_index)
            btn.scroll_into_view_if_needed()
            with page.expect_download(timeout=config.timeout_ms) as dl_info:
                btn.click()
            download = dl_info.value
            
            ext = ".jpg"
            suggested = download.suggested_filename
            if suggested and "." in suggested:
                ext = "." + suggested.split(".")[-1]
            
            device_parts = device_name.split("-")
            branch_code = _sanitize_folder_name(device_parts[0].strip()) if len(device_parts) > 0 else "UNKNOWN"
            branch_name = _sanitize_folder_name(device_parts[1].strip())[:18] if len(device_parts) > 1 else "UNKNOWN"

            time_str = ""
            date_str = datetime.now().strftime("%d%m%Y")
            
            if suggested:
                match_time = re.search(r'(\d{1,2})_(\d{1,2})_(\d{1,2})', suggested)
                if match_time:
                    h, m, s = match_time.groups()
                    is_pm = "pm" in suggested.lower()
                    is_am = "am" in suggested.lower()
                    h = int(h)
                    if is_pm and h < 12:
                        h += 12
                    elif is_am and h == 12:
                        h = 0
                    time_str = f"{h:02d}{m}{s}"
                
                match_date = re.search(r'(\d{1,2})[/-](\d{1,2})[/-](\d{4})', suggested)
                if match_date:
                    d, mo, y = match_date.groups()
                    date_str = f"{int(d):02d}{int(mo):02d}{y}"
            
            if not time_str:
                time_str = datetime.now().strftime("%H%M%S")
                
            base_filename = f"{branch_code}_{branch_name}_{date_str}_{time_str}"
            filename = f"{base_filename}{ext}"
            
            counter = 1
            while (device_folder / filename).exists():
                filename = f"{base_filename}_{counter}{ext}"
                counter += 1
                
            save_path = device_folder / filename
            download.save_as(str(save_path))
            duration = time.time() - start_time
            
            # Check if downloaded file is an S3 error page / XML
            is_xml_error = False
            if filename.endswith(".xml") or filename.endswith(".html"):
                try:
                    if save_path.exists():
                        content = save_path.read_text(errors="ignore")
                        if "NoSuchKey" in content or "<Error>" in content:
                            is_xml_error = True
                except Exception:
                    pass

            if is_xml_error:
                logger.info(f"  ✗ {filename} - image not present on portal ({duration:.1f}s)")
                try:
                    save_path.unlink(missing_ok=True)
                except Exception as ue:
                    logger.debug(f"Failed to delete XML error file: {ue}")
                log_download(safe_device_name, filename, "SKIPPED", duration, "image not present")
            else:
                logger.info(f"  ✓ {filename} saved to {device_folder.name}/ ({duration:.1f}s)")
                log_download(safe_device_name, filename, "SUCCESS", duration, f"row={row_index+1} img={btn_idx+1}")
                checkpoint_manager.add_downloaded_image(filename)
                downloaded += 1
            page.wait_for_timeout(500)
        except Exception as e:
            duration = time.time() - start_time
            logger.error(f"  ✗ Failed image {btn_idx + 1} of row {row_index + 1}: {e}")
            log_download(safe_device_name, f"row{row_index+1}_img{btn_idx+1}", "FAILED", duration, str(e))

    return downloaded

def _download_all_from_modal(page: Page, device_folder: Path, device_name: str, row_index: int) -> int:
    """Fallback: clicks 'Download All' in the modal."""
    modal_sel = config.selectors["download"]["modal_container"]
    dl_all_sel = config.selectors["download"]["modal_download_all"]

    modal = page.locator(modal_sel).first
    dl_all_btn = modal.locator(dl_all_sel).first

    try:
        if not dl_all_btn.is_visible(timeout=3000):
            logger.warning(f"'Download All' button not visible for row {row_index + 1}.")
            return 0
    except Exception:
        return 0

    device_folder.mkdir(parents=True, exist_ok=True)
    start_time = time.time()
    safe_device_name = _sanitize_folder_name(device_name)
    current_time_str = datetime.now().strftime("%H%M")
    
    try:
        with page.expect_download(timeout=config.timeout_ms) as dl_info:
            dl_all_btn.click()
        download = dl_info.value
        
        ext = ".zip"
        suggested = download.suggested_filename
        if suggested and "." in suggested:
            ext = "." + suggested.split(".")[-1]
            
        device_parts = device_name.split("-")
        branch_code = _sanitize_folder_name(device_parts[0].strip()) if len(device_parts) > 0 else "UNKNOWN"
        branch_name = _sanitize_folder_name(device_parts[1].strip())[:18] if len(device_parts) > 1 else "UNKNOWN"

        time_str = ""
        date_str = datetime.now().strftime("%d%m%Y")
        
        if suggested:
            match_time = re.search(r'(\d{1,2})_(\d{1,2})_(\d{1,2})', suggested)
            if match_time:
                h, m, s = match_time.groups()
                is_pm = "pm" in suggested.lower()
                is_am = "am" in suggested.lower()
                h = int(h)
                if is_pm and h < 12:
                    h += 12
                elif is_am and h == 12:
                    h = 0
                time_str = f"{h:02d}{m}{s}"
            
            match_date = re.search(r'(\d{1,2})[/-](\d{1,2})[/-](\d{4})', suggested)
            if match_date:
                d, mo, y = match_date.groups()
                date_str = f"{int(d):02d}{int(mo):02d}{y}"
        
        if not time_str:
            time_str = datetime.now().strftime("%H%M%S")
            
        base_filename = f"{branch_code}_{branch_name}_{date_str}_{time_str}_all"
        filename = f"{base_filename}{ext}"
        
        counter = 1
        while (device_folder / filename).exists():
            filename = f"{base_filename}_{counter}{ext}"
            counter += 1
            
        save_path = device_folder / filename
        download.save_as(str(save_path))
        duration = time.time() - start_time
        logger.info(f"  ✓ Download All → {filename} ({duration:.1f}s)")
        log_download(safe_device_name, filename, "SUCCESS", duration, f"download_all row={row_index+1}")
        checkpoint_manager.add_downloaded_image(filename)
        return 1
    except Exception as e:
        duration = time.time() - start_time
        logger.error(f"'Download All' failed for row {row_index + 1}: {e}")
        log_download(safe_device_name, f"download_all_row{row_index+1}", "FAILED", duration, str(e))
        return 0

def download_device_screenshots(page: Page, device_name: str, downloaded_filenames: list) -> int:
    """
    For each result row across all pages:
      1. Clicks the blue download icon → SnapShots modal opens
      2. Downloads each image from the modal individually
      3. Closes the modal and moves to the next row
      4. Navigates to next page if table results span multiple pages
    Saves files to downloads/<YYYYMMDD>/
    Returns total count of downloaded images.
    """
    sel = config.selectors["download"]
    results_sel = sel["results_container"]
    row_sel = sel["row_selector"]

    folder_name = _sanitize_folder_name(device_name)
    date_folder = datetime.now().strftime("%Y%m%d")
    device_folder = config.download_dir / date_folder

    # Check and create the download directory explicitly
    if not device_folder.exists():
        logger.info(f"Creating new directory for device: '{device_folder}'")
        device_folder.mkdir(parents=True, exist_ok=True)
    else:
        logger.info(f"Directory already exists for device: '{device_folder}'")

    # 1. Wait for results container to be present
    try:
        page.wait_for_selector(results_sel, timeout=12000)
    except Exception:
        logger.warning(f"Results table container not found for '{device_name}'. No screenshots to download.")
        log_download(folder_name, "", "SKIPPED", 0.0, "Results table not loaded")
        return 0

    total_downloaded = 0
    page_num = 1
    max_pages = 50

    while page_num <= max_pages:
        logger.info(f"--- Processing Table Page {page_num} for device '{device_name}' ---")

        # Wait for loading spinner (.g-loader) to disappear on current page
        logger.info(f"Waiting for table loading spinner on page {page_num}...")
        max_wait_seconds = 90
        poll_interval = 2.0
        elapsed = 0.0
        
        page.wait_for_timeout(1000)
        
        while elapsed < max_wait_seconds:
            for no_data_text in ["No Results Found", "No data found", "No records"]:
                try:
                    if page.locator(f"text={no_data_text}").first.is_visible():
                        if page_num == 1:
                            logger.info(f"No screenshots found (matching '{no_data_text}') for device '{device_name}'.")
                            log_download(folder_name, "", "SKIPPED", elapsed, f"No screenshots on portal ({no_data_text})")
                            return 0
                        else:
                            logger.info(f"No further records found on page {page_num}.")
                            break
                except Exception:
                    pass

            loader_visible = False
            try:
                if page.locator(".g-loader").first.is_visible():
                    loader_visible = True
            except Exception:
                pass
                
            if not loader_visible:
                logger.info(f"Table loading spinner has disappeared for page {page_num}.")
                break
                
            page.wait_for_timeout(int(poll_interval * 1000))
            elapsed += poll_interval
            if int(elapsed) % 6 == 0:
                logger.info(f"Still waiting for page {page_num} loading spinner... ({int(elapsed)}s elapsed)")
                
        if elapsed >= max_wait_seconds:
            logger.warning(f"Timed out waiting {max_wait_seconds}s for page {page_num} spinner. Checking table anyway.")
            
        page.wait_for_timeout(1000)  # Wait for DOM to stabilize

        # Check for "No Results Found" on Page 1
        if page_num == 1:
            for no_data_text in ["No Results Found", "No data found", "No records"]:
                try:
                    if page.locator(f"text={no_data_text}").first.is_visible():
                        logger.info(f"No screenshots found (matching '{no_data_text}') for device '{device_name}'.")
                        log_download(folder_name, "", "SKIPPED", 0.0, f"No screenshots on portal ({no_data_text})")
                        return 0
                except Exception:
                    pass

        # Count rows and map headers to column indices
        start_time_idx = 4
        end_time_idx = 5
        try:
            headers = page.locator(f"{results_sel} table thead th")
            header_count = headers.count()
            for i in range(header_count):
                h_text = headers.nth(i).inner_text().strip().lower()
                if "start time" in h_text:
                    start_time_idx = i
                elif "end time" in h_text:
                    end_time_idx = i
        except Exception as e:
            logger.debug(f"Failed dynamically mapping headers: {e}. Falling back to default indices 4 and 5.")

        rows = page.locator(f"{results_sel} {row_sel}")
        row_count = rows.count()
        logger.info(f"Page {page_num}: Found {row_count} result row(s) for device '{device_name}'.")

        if row_count == 0:
            if page_num == 1:
                log_download(folder_name, "", "SKIPPED", 0.0, "Results table has 0 rows")
            break

        for row_idx in range(row_count):
            row = rows.nth(row_idx)

            # Extract start and end times to verify the time slot condition
            start_str, end_str = "", ""
            try:
                start_str = row.locator("td").nth(start_time_idx).inner_text().strip()
                end_str = row.locator("td").nth(end_time_idx).inner_text().strip()
            except Exception as e:
                logger.warning(f"Page {page_num} Row {row_idx + 1}: Failed to extract start/end time cells: {e}")

            # Check range: both must be between start and end time (inclusive)
            start_slots = [s.strip() for s in str(config.download_start_time).split(",") if s.strip()]
            end_slots = [e.strip() for e in str(config.download_end_time).split(",") if e.strip()]
            
            if len(start_slots) != len(end_slots):
                logger.warning(f"Mismatch in start slots ({len(start_slots)}) and end slots ({len(end_slots)}). Using first slot only.")
                start_slots = start_slots[:1] if start_slots else ["08:30"]
                end_slots = end_slots[:1] if end_slots else ["09:30"]
                
            slots = []
            for s_slot, e_slot in zip(start_slots, end_slots):
                try:
                    start_h, start_m = map(int, s_slot.split(":"))
                    end_h, end_m = map(int, e_slot.split(":"))
                    t_start = datetime_time(start_h, start_m)
                    t_end = datetime_time(end_h, end_m)
                    slots.append((t_start, t_end, s_slot, e_slot))
                except Exception as pe:
                    logger.warning(f"Failed parsing slot {s_slot} - {e_slot}: {pe}")
                    
            if not slots:
                slots = [(datetime_time(8, 30), datetime_time(9, 30), "08:30", "09:30")]
                
            try:
                row_start = datetime_time(*map(int, start_str.split(":")))
                row_end = datetime_time(*map(int, end_str.split(":")))
                
                in_any_slot = False
                for t_start, t_end, s_slot, e_slot in slots:
                    if (t_start <= row_start <= t_end and t_start <= row_end <= t_end):
                        in_any_slot = True
                        break
                
                if not in_any_slot:
                    slots_str = ", ".join(f"{s[2]}-{s[3]}" for s in slots)
                    logger.info(f"Page {page_num} Row {row_idx + 1}/{row_count}: Skipping. Interval {start_str} - {end_str} is outside slots: {slots_str}.")
                    continue
            except Exception as e:
                logger.warning(f"Page {page_num} Row {row_idx + 1}/{row_count}: Skipping due to time parsing error on '{start_str}' - '{end_str}': {e}")
                continue

            last_td = row.locator("td:last-child")
            
            download_triggers = ["a", "button", "svg", "i", "span", "img"]
            icon = None
            for tag in download_triggers:
                try:
                    candidate = last_td.locator(tag).first
                    if candidate.count() > 0 and candidate.is_visible():
                        icon = candidate
                        break
                except Exception:
                    pass

            if not icon:
                try:
                    icon = last_td.locator("a, button").first
                except Exception:
                    pass

            try:
                visible = icon.is_visible(timeout=2000) if icon else False
            except Exception:
                visible = False

            if not visible:
                try:
                    cell_html = last_td.inner_html()
                except Exception:
                    cell_html = "unknown"
                logger.warning(f"Page {page_num} Row {row_idx + 1}: No download icon visible in last cell. TD HTML: {cell_html}")
                continue

            logger.info(f"Page {page_num} Row {row_idx + 1}/{row_count}: Opening SnapShots modal...")
            try:
                icon.scroll_into_view_if_needed()
                icon.click(force=True)
            except Exception as e:
                logger.warning(f"Page {page_num} Row {row_idx + 1}: Could not click download icon: {e}")
                continue

            count = _download_from_modal(page, device_folder, device_name, row_idx)
            total_downloaded += count

            _close_modal(page)
            page.wait_for_timeout(800)

        # Record first row signature to verify page content changes upon advancing
        first_row_sig = ""
        if row_count > 0:
            try:
                first_row_sig = rows.first.inner_text().strip()
            except Exception:
                pass

        # Check for Next Page button to iterate pagination
        next_btn = None
        next_selectors = [
            "ul.pagination li.page-item:not(.disabled) a.page-link:has-text('›')",
            "ul.pagination li.page-item:not(.disabled) a.page-link:has-text('Next')",
            "ul.pagination li.page-item:not(.disabled) button:has-text('Next')",
            ".pagination li:not(.disabled):not(.active) a[aria-label='Next']",
            "ul.pagination li.active + li:not(.disabled) a",
            "button.page-link:has-text('Next'):not([disabled])",
            "a.page-link:has-text('›'):not(.disabled)",
            ".pagination-next:not(.disabled)",
            "a[rel='next']:not(.disabled)",
            "button[aria-label='Next page']:not([disabled])"
        ]

        for p_sel in next_selectors:
            try:
                candidate = page.locator(p_sel).first
                if candidate.count() > 0 and candidate.is_visible():
                    disabled_attr = candidate.get_attribute("disabled")
                    aria_disabled = candidate.get_attribute("aria-disabled") or ""
                    
                    parent_li = candidate.locator("xpath=ancestor::li[1]")
                    li_class = ""
                    if parent_li.count() > 0:
                        li_class = parent_li.get_attribute("class") or ""
                        if not aria_disabled:
                            aria_disabled = parent_li.get_attribute("aria-disabled") or ""
                            
                    if "disabled" in li_class or aria_disabled == "true" or disabled_attr is not None:
                        continue

                    next_btn = candidate
                    break
            except Exception:
                pass

        if next_btn and next_btn.is_visible():
            logger.info(f"Found active Next Page button. Advancing to page {page_num + 1}...")
            try:
                next_btn.scroll_into_view_if_needed()
                next_btn.click(force=True)
                page.wait_for_timeout(1500)
                
                # Check if first row signature changed on new page
                new_rows = page.locator(f"{results_sel} {row_sel}")
                new_sig = ""
                if new_rows.count() > 0:
                    try:
                        new_sig = new_rows.first.inner_text().strip()
                    except Exception:
                        pass
                        
                if first_row_sig and new_sig and new_sig == first_row_sig:
                    logger.info(f"Table row content did not change after clicking Next Page. Reached last page at page {page_num}.")
                    break
                    
                page_num += 1
            except Exception as pe:
                logger.warning(f"Failed clicking Next Page button on page {page_num}: {pe}")
                break
        else:
            logger.info(f"No active Next Page button found after page {page_num}. Completed table pagination.")
            break

    if total_downloaded == 0:
        log_download(folder_name, "", "SKIPPED", 0.0, "All rows outside configured slots or empty")

    logger.info(f"Done. {total_downloaded} image(s) saved to '{folder_name}/' across {page_num} page(s).")
    return total_downloaded
