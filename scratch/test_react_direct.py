import sys
from playwright.sync_api import sync_playwright
from src.config import config

def test_direct_change():
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
        
        # Test Direct onChange call on From Date
        print("\n--- Testing Direct React onChange call on From Date ---")
        try:
            page.locator(start_sel).evaluate(
                """(el, val) => {
                    const keys = Object.keys(el);
                    const propsKey = keys.find(k => k.startsWith('__reactProps$'));
                    if (propsKey && el[propsKey]) {
                        console.log("Found React props keys:", propsKey);
                        // Trigger onChange
                        if (typeof el[propsKey].onChange === 'function') {
                            el[propsKey].onChange({ target: { value: val } });
                            console.log("Fired onChange successfully.");
                        } else {
                            console.log("onChange is not a function:", typeof el[propsKey].onChange);
                        }
                    } else {
                        console.log("React props key not found.");
                    }
                }""",
                test_val
            )
            page.wait_for_timeout(1000)
            print(f"From Date value: '{page.locator(start_sel).input_value()}'")
        except Exception as e:
            print(f"Direct onChange failed: {e}")
            
        # Let's also try Method D: Select all + Backspace + Type + Blur on To Date using standard playwright fill
        print("\n--- Testing Method D (Focus + clear + Type slashes) on To Date ---")
        try:
            page.locator(end_sel).click(force=True)
            page.locator(end_sel).focus()
            page.locator(end_sel).fill(test_val)
            page.locator(end_sel).press("Tab")
            page.wait_for_timeout(1000)
            print(f"To Date value: '{page.locator(end_sel).input_value()}'")
        except Exception as e:
            print(f"Method D failed: {e}")

        # Wait and read final screen values
        page.wait_for_timeout(3000)
        print("\n--- Final Screen Values ---")
        print(f"From Date: '{page.locator(start_sel).input_value()}'")
        print(f"To Date: '{page.locator(end_sel).input_value()}'")
        
        context.close()

if __name__ == "__main__":
    test_direct_change()
