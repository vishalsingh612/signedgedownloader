import sys
from playwright.sync_api import sync_playwright
from src.config import config

def dump_react_props():
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
            # Dump the React props properties
            props = page.locator(start_sel).first.evaluate(
                """el => {
                    const keys = Object.keys(el);
                    const propsKey = keys.find(k => k.startsWith('__reactProps$'));
                    if (!propsKey) return { error: "No react props found" };
                    
                    const reactProps = el[propsKey];
                    const propDetails = {};
                    for (let prop in reactProps) {
                        const val = reactProps[prop];
                        if (typeof val === 'function') {
                            propDetails[prop] = `Function: ${val.toString().slice(0, 100)}...`;
                        } else if (typeof val === 'object' && val !== null) {
                            try {
                                propDetails[prop] = JSON.stringify(val);
                            } catch (e) {
                                propDetails[prop] = `Object (non-serializable): ${Object.keys(val)}`;
                            }
                        } else {
                            propDetails[prop] = val;
                        }
                    }
                    return propDetails;
                }"""
            )
            print("\n--- React Props Details ---")
            for k, v in props.items():
                print(f"{k}: {v}")
                
        except Exception as e:
            print(f"Failed to dump React props: {e}")
            
        context.close()

if __name__ == "__main__":
    dump_react_props()
