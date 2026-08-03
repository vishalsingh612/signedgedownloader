import sys
from playwright.sync_api import sync_playwright
from src.config import config

def test_react_dates():
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
        test_val = "31/07/2026"
        
        print("\n--- Initial Values ---")
        print(f"From Date: '{page.locator(start_sel).input_value()}'")
        print(f"To Date: '{page.locator(end_sel).input_value()}'")
        
        # Test Method A (React-Safe JS Setter + Dispatch Events + Blur) on From Date
        print("\n--- Testing Method A (React-Safe JS + Events + Blur) on From Date ---")
        try:
            page.locator(start_sel).evaluate(
                """(el, val) => {
                    const setter = Object.getOwnPropertyDescriptor(window.HTMLInputElement.prototype, 'value').set;
                    setter.call(el, val);
                    el.dispatchEvent(new Event('input', { bubbles: true }));
                    el.dispatchEvent(new Event('change', { bubbles: true }));
                    el.dispatchEvent(new Event('blur', { bubbles: true }));
                }""",
                test_val
            )
            page.wait_for_timeout(1000)
            print(f"From Date value after Method A: '{page.locator(start_sel).input_value()}'")
        except Exception as e:
            print(f"Method A failed: {e}")
            
        # Test Method B (Focus + Select All + send_character + Tab) on To Date
        print("\n--- Testing Method B (Focus + Keyboard Typing + Tab Out) on To Date ---")
        try:
            page.locator(end_sel).focus()
            page.wait_for_timeout(200)
            
            # Select all text and backspace
            page.keyboard.press("Meta+A")
            page.keyboard.press("Control+A")
            page.keyboard.press("Backspace")
            page.wait_for_timeout(200)
            
            # Send characters using keyboard.type
            page.keyboard.type(test_val, delay=50)
                
            page.wait_for_timeout(500)
            # Press Tab to blur the field
            page.keyboard.press("Tab")
            page.wait_for_timeout(1000)
            print(f"To Date value after Method B: '{page.locator(end_sel).input_value()}'")
        except Exception as e:
            print(f"Method B failed: {e}")
            
        # Wait and read final screen values
        page.wait_for_timeout(3000)
        print("\n--- Final Screen Values ---")
        print(f"From Date: '{page.locator(start_sel).input_value()}'")
        print(f"To Date: '{page.locator(end_sel).input_value()}'")
        
        context.close()

if __name__ == "__main__":
    test_react_dates()
