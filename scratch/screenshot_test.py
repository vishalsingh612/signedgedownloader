import sys
from playwright.sync_api import sync_playwright
from src.config import config

def run_screenshot_test():
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
        end_sel = "input[placeholder='To Date*']"
        
        # Capture initial state screenshot
        print("Taking initial screenshot...")
        page.screenshot(path="screenshots/date_initial.png")
        
        # Test React-Safe JS injection
        print("Injecting date values via JS...")
        val = "31/07/2026"
        for sel in [start_sel, end_sel]:
            page.locator(sel).evaluate(
                """(el, val) => {
                    const setter = Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, 'value').set;
                    setter.call(el, val);
                    el.dispatchEvent(new Event('input', { bubbles: true }));
                    el.dispatchEvent(new Event('change', { bubbles: true }));
                    el.dispatchEvent(new Event('blur', { bubbles: true }));
                }""",
                val
            )
            
        page.wait_for_timeout(2000)
        
        # Capture final state screenshot
        print("Taking final screenshot...")
        page.screenshot(path="screenshots/date_final.png")
        
        print("Reading values from DOM:")
        print("From Date:", page.locator(start_sel).evaluate("el => el.value"))
        print("To Date:", page.locator(end_sel).evaluate("el => el.value"))
        
        context.close()

if __name__ == "__main__":
    run_screenshot_test()
