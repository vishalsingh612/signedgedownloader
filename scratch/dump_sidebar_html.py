import sys
from playwright.sync_api import sync_playwright
from src.config import config

def dump_sidebar():
    with sync_playwright() as p:
        print("Launching browser...")
        context = p.chromium.launch_persistent_context(
            user_data_dir=str(config.browser_profile_dir),
            headless=False,
            viewport={"width": 1280, "height": 800}
        )
        page = context.pages[0] if context.pages else context.new_page()
        page.goto(config.portal_url)
        
        print("\nPress ENTER in this terminal once the Dashboard is open on your screen...")
        input()
        
        print("\nDumping sidebar items HTML...")
        
        # Select all list items in the sidebar
        items = page.locator("ul.navbar-nav li, li.nav-item")
        print(f"Found {items.count()} sidebar items:")
        for i in range(items.count()):
            el = items.nth(i)
            html = el.inner_html()
            class_attr = el.get_attribute("class") or ""
            print(f"\n--- Item {i} (class='{class_attr}') ---")
            print(html.strip())
            
        # Also let's check for the toggle button at the top left
        print("\n--- Checking for potential sidebar expand toggle buttons ---")
        toggle_buttons = page.locator("button, div").filter(has_text=">")
        for i in range(toggle_buttons.count()):
            btn = toggle_buttons.nth(i)
            box = btn.bounding_box()
            if box and box["x"] < 150 and box["y"] < 100:
                print(f"Toggle Candidate {i}: tag='{btn.evaluate('el => el.tagName')}', class='{btn.get_attribute('class')}', box={box}")

        context.close()

if __name__ == "__main__":
    dump_sidebar()
