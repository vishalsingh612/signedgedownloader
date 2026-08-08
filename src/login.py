import time
from playwright.sync_api import Page
from src.config import config
from src.logger import logger
from src.notifier import notifier

def is_logged_in(page: Page) -> bool:
    """Checks if the user is currently logged in by looking for dashboard/profile elements."""
    dashboard_sel = config.selectors["login"]["dashboard_indicator"]
    email_sel = config.selectors["login"]["email_input"]
    password_sel = config.selectors["login"]["password_input"]
    try:
        # Give a small buffer for page to stabilize
        page.wait_for_timeout(2000)
        
        # If the login inputs are visible, we are definitely NOT logged in!
        if page.locator(email_sel).is_visible() or page.locator(password_sel).is_visible():
            return False
            
        # Check if dashboard selector (logout link, user profile) is visible
        if page.locator(dashboard_sel).is_visible():
            return True
            
        # Fallback URL check
        url_lower = page.url.lower()
        if not url_lower or "about:blank" in url_lower:
            return False
            
        if "login" not in url_lower and ("dashboard" in url_lower or "home" in url_lower or "customer" in url_lower or "playback" in url_lower):
            # Verify we aren't still at the login screen
            if not page.locator(email_sel).is_visible():
                return True
                
        return False
    except Exception:
        return False

def login(page: Page) -> bool:
    """
    Handles logging into the Panasonic Signedge Portal.
    Detects if session is active by navigating to the login page first.
    If session is active, the portal redirects to the dashboard, and we skip login.
    If session is not active, we proceed to fill credentials and log in.
    """
    login_url = config.portal_url
    logger.info(f"Checking session by navigating directly to login page: {login_url}")
    try:
        page.goto(login_url)
        # Give a small buffer for redirects/caching to settle
        page.wait_for_timeout(3000)
        
        # Wait up to 10 seconds for either the login form or the dashboard logout indicator to appear
        email_sel = config.selectors["login"]["email_input"]
        dashboard_sel = config.selectors["login"]["dashboard_indicator"]
        page.wait_for_selector(f"{email_sel}, {dashboard_sel}", timeout=10000)
    except Exception:
        pass
    
    url_lower = page.url.lower()
    email_sel = config.selectors["login"]["email_input"]
    password_sel = config.selectors["login"]["password_input"]
    dashboard_sel = config.selectors["login"]["dashboard_indicator"]
    
    # Check if we were redirected away from the login page to a dashboard/home/playback page
    is_logged_in_redirect = (
        "login" not in url_lower 
        and ("dashboard" in url_lower or "home" in url_lower or "customer" in url_lower or "playback" in url_lower)
    )
    
    # Or if the dashboard indicator is visible and login fields are not
    has_dashboard_element = page.locator(dashboard_sel).count() > 0 and page.locator(dashboard_sel).first.is_visible()
    has_login_fields = page.locator(email_sel).is_visible() or page.locator(password_sel).is_visible()
    
    if (is_logged_in_redirect or has_dashboard_element) and not has_login_fields:
        logger.info("Existing valid session detected (redirected away from login). Login skipped.")
        return True
    
    logger.info("No active session detected. Attempting login form fill...")
    # Since we are already on the login page (or page.goto(login_url) was already called),
    # we don't need to do page.goto(config.portal_url) again unless we somehow got redirected to a 404 or something weird.
    if "login" not in url_lower:
        logger.info(f"Currently at '{url_lower}'. Navigating to login page: {login_url}")
        page.goto(login_url)
        page.wait_for_timeout(2000)
    
    try:
        # Wait for either the login form OR the dashboard indicator (in case of redirect)
        email_sel = config.selectors["login"]["email_input"]
        dashboard_sel = config.selectors["login"]["dashboard_indicator"]
        combined_sel = f"{email_sel}, {dashboard_sel}"
        
        logger.info("Waiting for login page or dashboard redirect...")
        page.wait_for_selector(combined_sel, timeout=15000)
        
        # If dashboard selector is present, we are already logged in
        if page.locator(dashboard_sel).count() > 0 or not page.locator(email_sel).is_visible():
            logger.info("Active session detected (redirected to dashboard). Login skipped.")
            return True
            
        # Fill email
        page.locator(email_sel).fill(config.portal_email)
        
        # Fill password
        pass_sel = config.selectors["login"]["password_input"]
        page.locator(pass_sel).fill(config.portal_password)

        # Check if reCAPTCHA is visible/present on the page
        recaptcha_selectors = [
            "iframe[src*='recaptcha']",
            "div.g-recaptcha",
            "iframe[title*='reCAPTCHA']",
            ".g-recaptcha"
        ]
        has_recaptcha = False
        for sel in recaptcha_selectors:
            try:
                if page.locator(sel).count() > 0:
                    has_recaptcha = True
                    break
            except Exception:
                pass

        if has_recaptcha:
            logger.info("reCAPTCHA detected on page. Skipping auto-submit to allow manual reCAPTCHA solution.")
        else:
            # Click Submit
            submit_sel = config.selectors["login"]["submit_button"]
            page.locator(submit_sel).click()
            
            # Wait for navigation or loading
            page.wait_for_timeout(config.action_wait_ms)
    except Exception as e:
        logger.warning(f"Error filling credentials form: {e}. User might need to login manually.")
        try:
            screenshot_path = "screenshots/login_attempt_fail.png"
            page.screenshot(path=screenshot_path)
            logger.info(f"Saved debug screenshot to {screenshot_path}. Current URL: {page.url}")
        except Exception as se:
            logger.warning(f"Could not take debug screenshot: {se}")

    # Re-evaluate login status
    if is_logged_in(page):
        logger.info("Login successful.")
        return True

    # If still not logged in, we need manual intervention (reCAPTCHA or credentials error)
    reason = "reCAPTCHA check triggered or invalid credentials."
    logger.warning(f"Login failed: {reason}. Pausing automation for manual login...")
    
    # Send Email alert
    notifier.send_login_required(reason)
    
    # Polling Loop to wait for user to log in manually
    logged_in = False
    try:
        while not logged_in:
            logger.info("Automation paused. Waiting for manual login...")
            
            # Check if reCAPTCHA is solved in background and auto-submit
            captcha_response_sel = "textarea[id='g-recaptcha-response'], textarea[name='g-recaptcha-response']"
            try:
                if page.locator(captcha_response_sel).count() > 0:
                    response_val = page.locator(captcha_response_sel).evaluate("el => el.value")
                    if response_val and len(response_val.strip()) > 0:
                        logger.info("reCAPTCHA solved state detected! Auto-submitting login form...")
                        submit_sel = config.selectors["login"]["submit_button"]
                        page.locator(submit_sel).click()
                        # Wait a moment for page to process submit
                        page.wait_for_timeout(3000)
            except Exception as ce:
                logger.debug(f"Error checking reCAPTCHA response state: {ce}")

            page.wait_for_timeout(config.check_login_interval_seconds * 1000)
            
            # Check if browser was closed by the user
            if page.is_closed():
                logger.error("Browser page was closed by the user. Exiting login loop.")
                raise Exception("Browser page closed during manual login phase.")
                
            if is_logged_in(page):
                logger.info("Manual login detected! Resuming automation...")
                logged_in = True
                break
    except KeyboardInterrupt:
        logger.warning("Manual login wait interrupted by user.")
        raise
        
    return logged_in
