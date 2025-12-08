import os
import asyncio
from typing import Optional
from contextlib import asynccontextmanager
from playwright.async_api import async_playwright, Browser, BrowserContext, Page, Playwright


class BrowserManager:
    """
    Manages Playwright browser instances for web scraping.
    Handles browser lifecycle, contexts, and page creation.
    """

    _instance: Optional['BrowserManager'] = None
    _playwright: Optional[Playwright] = None
    _browser: Optional[Browser] = None

    def __init__(self):
        self.headless = os.getenv("HEADLESS", "true").lower() == "true"
        self.timeout = int(os.getenv("BROWSER_TIMEOUT", "30000"))

    @classmethod
    async def get_instance(cls) -> 'BrowserManager':
        """Get or create singleton instance."""
        if cls._instance is None:
            cls._instance = cls()
            await cls._instance._initialize()
        return cls._instance

    async def _initialize(self):
        """Initialize Playwright and browser."""
        if self._playwright is None:
            self._playwright = await async_playwright().start()
            self._browser = await self._playwright.chromium.launch(
                headless=self.headless,
                args=[
                    '--no-sandbox',
                    '--disable-setuid-sandbox',
                    '--disable-dev-shm-usage',
                    '--disable-accelerated-2d-canvas',
                    '--disable-gpu',
                ]
            )

    async def close(self):
        """Close browser and Playwright."""
        if self._browser:
            await self._browser.close()
            self._browser = None
        if self._playwright:
            await self._playwright.stop()
            self._playwright = None
        BrowserManager._instance = None

    @asynccontextmanager
    async def new_context(self, storage_state: Optional[str] = None):
        """
        Create a new browser context with optional storage state.

        Args:
            storage_state: Path to storage state file for session persistence
        """
        if self._browser is None:
            await self._initialize()

        context = await self._browser.new_context(
            viewport={'width': 1920, 'height': 1080},
            user_agent='Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            storage_state=storage_state if storage_state and os.path.exists(storage_state) else None,
        )

        context.set_default_timeout(self.timeout)

        try:
            yield context
        finally:
            await context.close()

    @asynccontextmanager
    async def new_page(self, context: Optional[BrowserContext] = None):
        """
        Create a new page, optionally within an existing context.

        Args:
            context: Existing browser context (creates new one if None)
        """
        if context:
            page = await context.new_page()
            try:
                yield page
            finally:
                await page.close()
        else:
            async with self.new_context() as ctx:
                page = await ctx.new_page()
                try:
                    yield page
                finally:
                    await page.close()

    async def save_storage_state(self, context: BrowserContext, path: str):
        """Save browser context storage state (cookies, localStorage) to file."""
        await context.storage_state(path=path)

    @staticmethod
    async def wait_for_navigation(page: Page, timeout: int = 30000):
        """Wait for navigation to complete."""
        try:
            await page.wait_for_load_state('networkidle', timeout=timeout)
        except Exception:
            await page.wait_for_load_state('domcontentloaded', timeout=timeout)

    @staticmethod
    async def safe_click(page: Page, selector: str, timeout: int = 10000):
        """Safely click an element, waiting for it to be visible first."""
        await page.wait_for_selector(selector, state='visible', timeout=timeout)
        await page.click(selector)

    @staticmethod
    async def safe_fill(page: Page, selector: str, value: str, timeout: int = 10000):
        """Safely fill an input field."""
        await page.wait_for_selector(selector, state='visible', timeout=timeout)
        await page.fill(selector, value)

    @staticmethod
    async def safe_get_text(page: Page, selector: str, timeout: int = 5000) -> Optional[str]:
        """Safely get text content from an element."""
        try:
            await page.wait_for_selector(selector, state='visible', timeout=timeout)
            element = await page.query_selector(selector)
            if element:
                return await element.text_content()
        except Exception:
            pass
        return None

    @staticmethod
    async def safe_get_attribute(page: Page, selector: str, attribute: str, timeout: int = 5000) -> Optional[str]:
        """Safely get an attribute from an element."""
        try:
            await page.wait_for_selector(selector, state='visible', timeout=timeout)
            element = await page.query_selector(selector)
            if element:
                return await element.get_attribute(attribute)
        except Exception:
            pass
        return None


# Global browser manager instance
browser_manager: Optional[BrowserManager] = None


async def get_browser_manager() -> BrowserManager:
    """Get the global browser manager instance."""
    global browser_manager
    if browser_manager is None:
        browser_manager = await BrowserManager.get_instance()
    return browser_manager


async def cleanup_browser():
    """Cleanup browser resources."""
    global browser_manager
    if browser_manager:
        await browser_manager.close()
        browser_manager = None
