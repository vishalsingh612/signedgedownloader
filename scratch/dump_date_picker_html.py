import sys
from playwright.sync_api import sync_playwright
from src.config import config

def dump_date_pickers():
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
        
        # Select all inputs with startDate name
        inputs = page.locator("input[name='startDate'], input#floatingSelect, input")
        print(f"\nFound {inputs.count()} inputs total on page:")
        for i in range(inputs.count()):
            el = inputs.nth(i)
            name = el.get_attribute("name") or ""
            placeholder = el.get_attribute("placeholder") or ""
            id_attr = el.get_attribute("id") or ""
            class_attr = el.get_attribute("class") or ""
            type_attr = el.get_attribute("type") or ""
            
            # Print outer HTML of parents to see structural wrapping
            outer_html = el.evaluate("el => el.outerHTML")
            parent_html = el.locator("xpath=..").evaluate("el => el.outerHTML")
            
            print(f"\n--- Input {i} (id='{id_attr}', name='{name}', placeholder='{placeholder}') ---")
            print(f"Type: '{type_attr}', Class: '{class_attr}'")
            print("Element HTML:", outer_html)
            print("Parent HTML (truncated):", parent_html[:300])

        context.close()

if __name__ == "__main__":
    dump_date_pickers()
