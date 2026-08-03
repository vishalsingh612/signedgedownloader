import sys
from playwright.sync_api import sync_playwright
from src.config import config

def test_dates():
    with sync_playwright() as p:
        print("Launching browser...")
        context = p.chromium.launch_persistent_context(
            user_data_dir=str(config.browser_profile_dir),
            headless=False,
            viewport={"width": 1280, "height": 800}
        )
        page = context.pages[0] if context.pages else context.new_page()
        
        # Navigate directly to content playback
        url = "https://signedge.in.panasonic.com/customer/midlandmicrofinltd/report/content-playback"
        print(f"Navigating to {url}...")
        page.goto(url)
        page.wait_for_timeout(4000)
        
        start_sel = "input[placeholder='From Date*']"
        end_sel = "input[placeholder='To Date*']"
        
        print("\n--- Initial Values ---")
        try:
            print(f"From Date value: '{page.locator(start_sel).input_value()}'")
            print(f"To Date value: '{page.locator(end_sel).input_value()}'")
        except Exception as e:
            print(f"Error reading initial values: {e}")
            
        test_val = "31/07/2026"
        
        # Method 1: Click, Select All, Backspace, Type
        print(f"\n--- Testing Method 1 (Select All + Type '{test_val}') ---")
        try:
            page.locator(start_sel).click(force=True)
            # Select all using keyboard
            page.keyboard.press("Meta+A") # Mac
            page.keyboard.press("Control+A") # Win/Linux fallback
            page.keyboard.press("Backspace")
            page.locator(start_sel).press_sequentially(test_val, delay=100)
            page.keyboard.press("Enter")
            print(f"After Method 1 value: '{page.locator(start_sel).input_value()}'")
        except Exception as e:
            print(f"Method 1 failed: {e}")
            
        # Method 2: Click, clear, fill
        print(f"\n--- Testing Method 2 (Fill '{test_val}') ---")
        try:
            page.locator(end_sel).click(force=True)
            page.locator(end_sel).fill("")
            page.locator(end_sel).fill(test_val)
            print(f"After Method 2 value: '{page.locator(end_sel).input_value()}'")
        except Exception as e:
            print(f"Method 2 failed: {e}")
            
        # Wait to let UI settle and inspect visually
        print("\nKeeping page open for 5 seconds...")
        page.wait_for_timeout(5000)
        
        print("\nFinal values on screen:")
        print(f"From Date: '{page.locator(start_sel).input_value()}'")
        print(f"To Date: '{page.locator(end_sel).input_value()}'")
        
        context.close()

if __name__ == "__main__":
    test_dates()
