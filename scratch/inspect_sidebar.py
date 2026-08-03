import sys
from playwright.sync_api import sync_playwright
from src.config import config

def inspect_sidebar():
    with sync_playwright() as p:
        print("Launching Chromium headful to inspect sidebar...")
        context = p.chromium.launch_persistent_context(
            user_data_dir=str(config.browser_profile_dir),
            headless=False,
            viewport={"width": 1280, "height": 800}
        )
        
        page = context.pages[0] if context.pages else context.new_page()
        page.goto(config.portal_url)
        
        print("\nACTION REQUIRED:")
        print("1. Solve reCAPTCHA and log in if you are on the login page.")
        print("2. Keep the main Dashboard open on your screen (where you see the left sidebar icons).")
        print("3. Come back to this terminal and press ENTER to scan the sidebar.")
        
        input("\nPress ENTER here once you are logged in on the Dashboard...")
        
        print("\nScanning sidebar elements...")
        
        # Scrape elements on the left side of the page (typically nav, aside, or divs with class sidebar)
        print("\n--- Scanning Navigation / Sidebar HTML Elements ---")
        sidebar_selectors = [
            "nav", "aside", ".sidebar", ".navigation", ".aside", ".menu", 
            "div.flex-column", "div.border-end", ".navbar-nav"
        ]
        
        # Let's dump all anchor links and buttons inside the left side
        # Find elements in the left 100px of the viewport
        links = page.locator("a, button, div, li")
        found = 0
        for i in range(links.count()):
            el = links.nth(i)
            try:
                box = el.bounding_box()
                if box and box["x"] < 150 and box["width"] > 0:
                    tag = el.evaluate("el => el.tagName").lower()
                    class_attr = el.get_attribute("class") or ""
                    id_attr = el.get_attribute("id") or ""
                    text = el.inner_text().strip().replace("\n", " ")[:60]
                    # Print buttons and links or elements with classes
                    if tag in ["a", "button", "li", "span"] or "btn" in class_attr or "menu" in class_attr:
                        print(f"Selector candidate [{tag}]: id='{id_attr}', class='{class_attr}', text='{text}'")
                        found += 1
            except Exception:
                pass
                
        print(f"\nScan complete. Found {found} elements on the left sidebar region.")
        context.close()

if __name__ == "__main__":
    inspect_sidebar()
