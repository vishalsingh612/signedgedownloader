from playwright.sync_api import sync_playwright

def inspect():
    with sync_playwright() as p:
        print("Launching browser...")
        browser = p.chromium.launch(headless=True)
        page = browser.new_page()
        url = "https://signedge.in.panasonic.com/customer/midlandmicrofinltd/login"
        print(f"Navigating to {url}...")
        page.goto(url)
        page.wait_for_timeout(5000)
        
        # Scrape and print information about inputs and forms
        print("\n--- PAGE URL ---")
        print(page.url)
        
        print("\n--- FORM INPUTS ---")
        inputs = page.locator("input")
        print(f"Found {inputs.count()} input elements:")
        for i in range(inputs.count()):
            el = inputs.nth(i)
            name = el.get_attribute("name")
            type_attr = el.get_attribute("type")
            id_attr = el.get_attribute("id")
            placeholder = el.get_attribute("placeholder")
            class_attr = el.get_attribute("class")
            print(f"Input {i}: id='{id_attr}', name='{name}', type='{type_attr}', placeholder='{placeholder}', class='{class_attr}'")
            
        print("\n--- BUTTONS ---")
        buttons = page.locator("button, input[type='button'], input[type='submit']")
        print(f"Found {buttons.count()} buttons:")
        for i in range(buttons.count()):
            el = buttons.nth(i)
            text = el.inner_text().strip() or el.get_attribute("value") or ""
            id_attr = el.get_attribute("id")
            class_attr = el.get_attribute("class")
            print(f"Button {i}: id='{id_attr}', text='{text}', class='{class_attr}'")
            
        browser.close()

if __name__ == "__main__":
    inspect()
