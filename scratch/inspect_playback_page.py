import sys
from playwright.sync_api import sync_playwright
from src.config import config

def interactive_inspect():
    with sync_playwright() as p:
        print("Launching Chromium headful with your persistent profile...")
        # Launch using the profile directory so your session is loaded
        context = p.chromium.launch_persistent_context(
            user_data_dir=str(config.browser_profile_dir),
            headless=False,
            viewport={"width": 1280, "height": 800}
        )
        
        page = context.pages[0] if context.pages else context.new_page()
        
        print("\n==================================================================")
        print(f"Opening portal URL: {config.portal_url}")
        print("==================================================================")
        page.goto(config.portal_url)
        
        print("\nACTION REQUIRED ON YOUR SCREEN:")
        print("1. If not logged in, please enter credentials and solve reCAPTCHA.")
        print("2. Navigate to the 'Reports -> Content Playback' page.")
        print("3. Keep that page open on your screen.")
        print("4. Come back to this terminal and press ENTER to dump selectors.")
        
        # Wait for user input in console
        input("\nPress ENTER here once you are on the Content Playback page...")
        
        print("\nScanning page elements... Please wait...")
        
        print("\n--- Current Page URL ---")
        print(page.url)
        
        # Scan form controls (divs and inputs)
        print("\n--- Form Inputs & Placeholders ---")
        inputs = page.locator("input, select, textarea, div[role='combobox'], [class*='select'], [class*='dropdown']")
        print(f"Found {inputs.count()} input/dropdown elements:")
        for i in range(inputs.count()):
            el = inputs.nth(i)
            tag = el.evaluate("el => el.tagName").lower()
            id_attr = el.get_attribute("id") or ""
            name = el.get_attribute("name") or ""
            class_attr = el.get_attribute("class") or ""
            placeholder = el.get_attribute("placeholder") or ""
            role = el.get_attribute("role") or ""
            text = el.inner_text().strip().replace('\n', ' ')[:100]
            
            # Print only relevant fields to keep output clean
            if class_attr or id_attr or name:
                print(f"Element {i} [{tag}]: id='{id_attr}', name='{name}', role='{role}', placeholder='{placeholder}', class='{class_attr}'")
                if text:
                    print(f"  -> Text: {text}")

        # Scan for date pickers
        print("\n--- Potential Date Inputs ---")
        date_inputs = page.locator("input[type='date'], input[placeholder*='Date'], input[placeholder*='date'], input[id*='date'], input[name*='date']")
        for i in range(date_inputs.count()):
            el = date_inputs.nth(i)
            print(f"Date Field {i}: id='{el.get_attribute('id')}', name='{el.get_attribute('name')}', placeholder='{el.get_attribute('placeholder')}', class='{el.get_attribute('class')}'")

        # Scan buttons
        print("\n--- Buttons ---")
        buttons = page.locator("button, input[type='button'], input[type='submit'], .btn, [class*='button']")
        for i in range(buttons.count()):
            el = buttons.nth(i)
            print(f"Button {i}: id='{el.get_attribute('id')}', text='{el.inner_text().strip()}', class='{el.get_attribute('class')}'")

        context.close()
        print("\nInspection finished context closed.")

if __name__ == "__main__":
    interactive_inspect()
