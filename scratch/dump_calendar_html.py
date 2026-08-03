import sys
from playwright.sync_api import sync_playwright
from src.config import config

def dump_calendar():
    with sync_playwright() as p:
        print("Launching browser...")
        context = p.chromium.launch_persistent_context(
            user_data_dir=str(config.browser_profile_dir),
            headless=False,
            viewport={"width": 1280, "height": 800}
        )
        page = context.pages[0] if context.pages else context.new_page()
        
        url = "https://signedge.in.panasonic.com/customer/midlandmicrofinltd/report/content-playback"
        print(f"Navigating to {url}...")
        page.goto(url)
        page.wait_for_timeout(4000)
        
        start_sel = "input[placeholder='From Date*']"
        
        # Capture outer HTML of parent before click
        parent_before = page.locator(start_sel).locator("xpath=../../..").evaluate("el => el.outerHTML")
        print("\nParent HTML before click (length):", len(parent_before))
        
        print("Clicking From Date input...")
        page.locator(start_sel).click(force=True)
        page.wait_for_timeout(2000)
        
        # Take a screenshot to verify it opened
        page.screenshot(path="screenshots/calendar_opened.png")
        print("Screenshot of opened calendar saved to screenshots/calendar_opened.png")
        
        # Capture outer HTML of parent after click to see new calendar nodes
        parent_after = page.locator(start_sel).locator("xpath=../../..").evaluate("el => el.outerHTML")
        print("Parent HTML after click (length):", len(parent_after))
        
        # Print differences or look for calendar divs anywhere on the page
        print("\nSearching for calendar-like elements on the entire page:")
        divs = page.locator("div")
        calendar_divs = []
        for i in range(divs.count()):
            try:
                el = divs.nth(i)
                html = el.evaluate("el => el.outerHTML")
                # Look for calendar indicators in class or id
                class_attr = el.get_attribute("class") or ""
                id_attr = el.get_attribute("id") or ""
                
                if any(x in class_attr.lower() or x in id_attr.lower() for x in ["calendar", "datepicker", "date-picker", "day", "month", "year"]):
                    # Keep unique top-level calendar divs
                    if len(html) < 2000 and "calendar" in class_attr.lower():
                        calendar_divs.append((class_attr, id_attr, html))
            except Exception:
                pass
                
        print(f"Found {len(calendar_divs)} calendar-related divs:")
        for idx, (cls, id_val, html) in enumerate(calendar_divs[:5]):
            print(f"\n--- Calendar Div {idx} (class='{cls}', id='{id_val}') ---")
            print(html)
            
        context.close()

if __name__ == "__main__":
    dump_calendar()
