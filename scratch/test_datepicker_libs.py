import sys
from playwright.sync_api import sync_playwright
from src.config import config

def test_libs():
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
        
        try:
            # Evaluate properties on the element to find library bindings
            info = page.locator(start_sel).first.evaluate(
                """el => {
                    const keys = Object.keys(el);
                    const reactFiberKey = keys.find(k => k.startsWith('__reactFiber$'));
                    const reactPropsKey = keys.find(k => k.startsWith('__reactProps$'));
                    const reactEventsKey = keys.find(k => k.startsWith('__reactEvents$'));
                    
                    return {
                        has_flatpickr: !!el._flatpickr,
                        has_datepicker: typeof el.datepicker !== 'undefined',
                        has_react_fiber: !!reactFiberKey,
                        has_react_props: !!reactPropsKey,
                        react_keys: keys.filter(k => k.includes('react')),
                        tagName: el.tagName,
                        value: el.value,
                        type: el.type,
                        classList: Array.from(el.classList)
                    };
                }"""
            )
            print("\n--- Diagnostic Info ---")
            for k, v in info.items():
                print(f"{k}: {v}")
                
        except Exception as e:
            print(f"Failed to inspect library bindings: {e}")
            
        context.close()

if __name__ == "__main__":
    test_libs()
