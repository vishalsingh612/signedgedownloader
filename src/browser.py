import sys
import traceback
from playwright.sync_api import sync_playwright, Playwright, BrowserContext, Page
from src.config import config
from src.logger import logger

class BrowserManager:
    def __init__(self):
        self.playwright = None
        self.context = None
        self.page = None

    def start(self, headless: bool = None) -> Page:
        """Launches Chromium with a persistent user profile and returns the active page."""
        if self.page:
            try:
                if not self.page.is_closed():
                    return self.page
            except Exception:
                pass
            self.page = None

        is_headless = config.headless if headless is None else headless
        logger.info(f"Starting browser context (headless={is_headless}, profile={config.browser_profile_dir})")

        try:
            # Cleanup Chromium lock files from previous interrupted runs to prevent profile locks/blank pages
            try:
                import os
                from pathlib import Path
                profile_dir = Path(config.browser_profile_dir)
                if profile_dir.exists():
                    for lock_name in ["SingletonLock", "SingletonSocket", "SingletonCookie", "lock"]:
                        lock_file = profile_dir / lock_name
                        if lock_file.exists() or lock_file.is_symlink():
                            logger.info(f"Removing old browser lock: {lock_name}")
                            if lock_file.is_symlink() or not lock_file.is_dir():
                                os.remove(lock_file)
            except Exception as le:
                logger.debug(f"Warning: Could not remove browser lock files: {le}")

            self.playwright = sync_playwright().start()
            
            # Setup launch arguments for stability and anti-detection.
            # Do NOT pass --no-sandbox or --disable-setuid-sandbox on Windows as it crashes file downloads.
            args = [
                "--disable-dev-shm-usage",
                "--disable-gpu",
                "--disable-blink-features=AutomationControlled"
            ]
            if sys.platform.startswith("linux"):
                args.extend(["--no-sandbox", "--disable-setuid-sandbox"])

            user_agent = (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
                if sys.platform.startswith("win")
                else "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
            )

            # Ensure download root exists
            config.download_dir.mkdir(parents=True, exist_ok=True)

            self.context = self.playwright.chromium.launch_persistent_context(
                user_data_dir=str(config.browser_profile_dir),
                headless=is_headless,
                args=args,
                downloads_path=str(config.download_dir),
                viewport={"width": 1280, "height": 800},
                accept_downloads=True,
                user_agent=user_agent
            )
            self.context.set_default_timeout(config.timeout_ms)

            # Get the first page or open a new page
            pages = self.context.pages
            if pages:
                self.page = pages[0]
            else:
                self.page = self.context.new_page()

            # Set default timeout
            self.page.set_default_timeout(config.timeout_ms)
            logger.info("Browser persistent context started successfully.")
            return self.page
        except Exception as e:
            logger.error(f"Failed to launch browser: {e}")
            logger.debug(traceback.format_exc())
            self.stop()
            raise

    def restart(self, headless: bool = None) -> Page:
        """Safely stops and restarts browser context."""
        logger.info("Restarting browser context...")
        self.stop()
        return self.start(headless=headless)

    def is_alive(self) -> bool:
        """Checks if current page and context are valid and not closed."""
        try:
            return bool(self.page and not self.page.is_closed() and self.context)
        except Exception:
            return False

    def stop(self):
        """Closes the page, browser context, and stops playwright."""
        logger.info("Stopping browser context...")
        try:
            if self.page:
                self.page.close()
        except Exception as e:
            logger.debug(f"Error closing page: {e}")
        finally:
            self.page = None

        try:
            if self.context:
                self.context.close()
        except Exception as e:
            logger.debug(f"Error closing browser context: {e}")
        finally:
            self.context = None

        try:
            if self.playwright:
                self.playwright.stop()
        except Exception as e:
            logger.debug(f"Error stopping playwright: {e}")
        finally:
            self.playwright = None
            
        logger.info("Browser context stopped.")

# Instantiate browser manager global instance
browser_manager = BrowserManager()
