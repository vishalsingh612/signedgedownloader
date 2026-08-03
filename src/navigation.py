from datetime import datetime, timedelta
from playwright.sync_api import Page
from src.config import config
from src.logger import logger

def get_target_date_obj() -> datetime:
    """
    Returns the target date object.
    On Mondays, returns Saturday (2 days ago).
    On other days, returns yesterday (1 day ago).
    """
    today = datetime.now()
    weekday = today.weekday()
    if weekday == 0:  # Monday
        return today - timedelta(days=2)  # Saturday
    return today - timedelta(days=1)  # Yesterday

def get_yesterday_dates():
    """Returns target date in various formats for date picker compatibility."""
    target_date = get_target_date_obj()
    return {
        "ddmmyyyy": target_date.strftime("%d%m%Y"),
        "dd_mm_yyyy": target_date.strftime("%d-%m-%Y"),
        "yyyy_mm_dd": target_date.strftime("%Y-%m-%d"),
        "slashes": target_date.strftime("%d/%m/%Y"),
        "display": target_date.strftime("%B %d, %Y")
    }


def clear_react_select(page: Page, input_selector: str):
    """Clears all selected items in a React-Select dropdown by clicking the clear indicator or tags."""
    try:
        # Parse the input element ID to find the react-select container parent
        input_id = input_selector.split("#")[-1]
        parent = page.locator(f"xpath=//input[@id='{input_id}']/ancestor::div[contains(@class, 'control') or contains(@class, 'container')][1]")
        
        # Check if there's a clear indicator on the right of the control
        clear_btn = parent.locator("div[class*='clear-indicator'], div[class*='ClearIndicator'], .react-select__clear-indicator")
        
        if clear_btn.count() > 0 and clear_btn.first.is_visible():
            clear_btn.first.click(force=True)
            page.wait_for_timeout(500)
            return
            
        # Fallback: Click the 'x' of each selected tag inside the control
        remove_btns = parent.locator("div[class*='multi-value__remove'], div[class*='multiValue__remove'], .react-select__multi-value__remove")
        count = remove_btns.count()
        for i in range(count):
            remove_btns.nth(0).click(force=True)
            page.wait_for_timeout(300)
    except Exception as e:
        logger.debug(f"Clear dropdown fallback triggered: {e}")

def navigate_to_content_playback(page: Page):
    """Navigates directly to the Content Playback page using the direct URL."""
    url = config.portal_playback_url
    if not url:
        url = config.portal_url.replace("/login", "/report/content-playback")

    logger.info(f"Navigating directly to Content Playback URL: {url}")

    try:
        page.goto(url)
        page.wait_for_timeout(config.action_wait_ms)
        logger.info("Successfully navigated to Content Playback page.")
    except Exception as e:
        logger.error(f"Navigation to Content Playback page failed: {e}")
        raise

def select_react_select_option(page, input_selector: str, option_text: str):
    """Fills a React-Select input and clicks the matching option in the dropdown list."""
    logger.info(f"Selecting custom dropdown option '{option_text}' via {input_selector}")
    
    # Wait for the input box
    page.wait_for_selector(input_selector, timeout=10000)
    input_el = page.locator(input_selector)
    
    # Extract unique code prefix (e.g. "B0006" or first 8 chars) to avoid search term typing issues
    import re
    match = re.match(r'^([a-zA-Z0-9]+)', option_text)
    search_term = match.group(1) if match else option_text[:8]
    
    # Focus input and open the menu by pressing ArrowDown
    input_el.click(force=True)
    input_el.press("ArrowDown")
    page.wait_for_timeout(500)
    
    # Fill search prefix
    input_el.fill("")
    input_el.press_sequentially(search_term, delay=80)
    page.wait_for_timeout(1500)
    
    # Check dropdown list options and click the matching one
    clicked = False
    option_sel = "div[id*='-option'], div[class*='-option'], .react-select__option"
    
    try:
        # Wait for options, if they don't show try ArrowDown again to open menu
        try:
            page.wait_for_selector(option_sel, timeout=4000)
        except Exception:
            input_el.press("ArrowDown")
            page.wait_for_selector(option_sel, timeout=3000)
            
        options = page.locator(option_sel)
        count = options.count()
        
        # Loop and click the option containing our search prefix (e.g. "B0003")
        for i in range(count):
            opt = options.nth(i)
            opt_text = opt.inner_text().strip()
            if search_term.lower() in opt_text.lower():
                opt.click(force=True)
                clicked = True
                logger.info(f"Selected dropdown option: '{opt_text}' matching prefix '{search_term}'")
                break
    except Exception as e:
        logger.debug(f"Dropdown options selection helper error: {e}")
        
    if not clicked:
        # Final Fallback: Press Enter
        logger.warning(f"Could not find option containing '{search_term}' in the list. Pressing Enter as final fallback...")
        input_el.press("Enter")
        
    page.wait_for_timeout(1000)


def click_react_calendar_date(page: Page, input_sel: str, target_date: datetime):
    """
    Opens the react-calendar popup for the given date input and clicks the target date.
    Navigates back/forward months as needed.
    """
    logger.info(f"Opening calendar for '{input_sel}' to pick {target_date.strftime('%d/%m/%Y')}")
    
    # Open the calendar. Try native click, dispatch click event, or evaluate click.
    cal_opened = False
    cal_nav_sel = ".react-calendar__navigation"
    
    for attempt in range(3):
        try:
            if attempt == 0:
                page.locator(input_sel).click(force=True)
            elif attempt == 1:
                page.locator(input_sel).dispatch_event("click")
            else:
                page.locator(input_sel).evaluate("el => el.click()")
            
            # Wait for calendar navigation to be visible
            page.locator(cal_nav_sel).first.wait_for(state="visible", timeout=3000)
            cal_opened = True
            break
        except Exception:
            logger.debug(f"Calendar open attempt {attempt + 1} failed. Retrying...")
            page.wait_for_timeout(1000)
            
    if not cal_opened:
        # Re-raise the visibility wait to let caller handle it or raise standard error
        page.locator(cal_nav_sel).first.wait_for(state="visible", timeout=6000)
    page.wait_for_timeout(500)  # Give React time to fully render


    # Navigate months until we are on the correct month/year
    target_label = target_date.strftime("%B %Y")  # e.g. "July 2026"
    max_nav = 24
    for _ in range(max_nav):
        # Safeguard: if calendar closes during navigation, reopen it
        try:
            if not page.locator(".react-calendar__navigation").first.is_visible():
                logger.info("Calendar closed unexpectedly during navigation. Re-opening...")
                page.locator(input_sel).click(force=True)
                page.locator(".react-calendar__navigation").first.wait_for(state="visible", timeout=6000)
                page.wait_for_timeout(400)
        except Exception:
            pass

        label = page.locator(".react-calendar__navigation__label__labelText--from").inner_text().strip()
        logger.info(f"Calendar currently showing: '{label}', target: '{target_label}'")
        if label == target_label:
            break
        try:
            current = datetime.strptime(label, "%B %Y")
        except ValueError:
            logger.warning(f"Could not parse calendar label: '{label}'")
            break
        if (current.year, current.month) > (target_date.year, target_date.month):
            page.locator(".react-calendar__navigation__prev-button").evaluate("el => el.click()")
        else:
            page.locator(".react-calendar__navigation__next-button").evaluate("el => el.click()")
        page.wait_for_timeout(600)


    # Wait for tiles to render for the target month
    page.wait_for_timeout(400)

    # Click the correct day tile using Playwright locator + JS contains on aria-label
    day_label_partial = target_date.strftime("%d %B %Y").lstrip("0")  # "31 July 2026"
    day_num = str(target_date.day)
    
    # Strategy 1: aria-label contains partial date string
    clicked = False
    tiles = page.locator("button.react-calendar__tile")
    count = tiles.count()
    logger.info(f"Found {count} calendar tiles. Looking for day '{day_num}' / aria-label containing '{day_label_partial}'")
    for i in range(count):
        tile = tiles.nth(i)
        aria = tile.get_attribute("aria-label") or ""
        if day_label_partial in aria:
            tile.click(force=True)
            clicked = True
            logger.info(f"Clicked tile with aria-label: '{aria}'")
            break

    # Strategy 2: exact abbr text match
    if not clicked:
        logger.warning(f"aria-label match failed, trying exact abbr text='{day_num}'...")
        for i in range(count):
            tile = tiles.nth(i)
            abbr = tile.locator("abbr")
            if abbr.count() > 0:
                text = abbr.inner_text().strip()
                if text == day_num:
                    tile.click(force=True)
                    clicked = True
                    logger.info(f"Clicked tile via abbr text '{day_num}' at index {i}")
                    break

    if not clicked:
        # Save a debug screenshot before raising
        safe_name = input_sel.replace("[","").replace("]","").replace("*","").replace("=","_").replace("'","")
        page.screenshot(path=f"screenshots/calendar_debug_{safe_name}.png")
        raise Exception(f"Could not find calendar tile for day '{day_num}' / aria containing '{day_label_partial}' among {count} tiles")
    
    page.wait_for_timeout(600)
    logger.info(f"Calendar date {target_date.strftime('%d/%m/%Y')} selected.")


def select_search_filters(page: Page, campaign_name: str) -> str:
    """
    Selects target date (yesterday / Saturday on Mondays) and the target campaign.
    Returns the target ddmmyyyy string.
    """
    dates = get_yesterday_dates()
    target_date = get_target_date_obj()
    logger.info(f"Setting dates to target date: {dates['display']}")

    start_date_sel = config.selectors["playback"]["date_start_input"]
    end_date_sel = config.selectors["playback"]["date_end_input"]
    campaign_sel = config.selectors["playback"]["campaign_dropdown"]

    try:
        # Use the react-calendar click strategy for both date inputs
        click_react_calendar_date(page, start_date_sel, target_date)
        click_react_calendar_date(page, end_date_sel, target_date)

        # Select Campaign
        select_react_select_option(page, campaign_sel, campaign_name)
        
        return dates["ddmmyyyy"]
    except Exception as e:
        logger.error(f"Failed to apply search filters: {e}")
        raise
