import sys
from playwright.sync_api import sync_playwright
from src.config import config

def dump_row():
    with sync_playwright() as p:
        print("Launching browser...")
        context = p.chromium.launch_persistent_context(
            user_data_dir=config.browser_profile_path,
            headless=False
        )
        page = context.pages[0]
        print("Navigating to Content Playback page...")
        page.goto("https://signedge.in.panasonic.com/customer/midlandmicrofinltd/report/content-playback")
        page.wait_for_timeout(5000)
        
        # Check if we are logged in, if not wait for user
        if "login" in page.url:
            print("Please log in manually on the browser window...")
            page.wait_for_url("**/report/content-playback", timeout=60000)
        
        print("Waiting for results table...")
        try:
            page.wait_for_selector(".table-responsive table tbody tr", timeout=20000)
            row = page.locator(".table-responsive table tbody tr").first
            last_td = row.locator("td:last-child")
            print("Last TD HTML:")
            print(last_td.inner_html())
        except Exception as e:
            print("Error finding row:", e)
            
        context.close()

if __name__ == "__main__":
    dump_row()
