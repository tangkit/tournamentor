import os
from typing import Optional, Any, Dict, List
from contextlib import asynccontextmanager
from notte_sdk import NotteClient


class NotteSession:
    """Wrapper around Notte session providing Playwright-like interface."""

    def __init__(self, session):
        self._session = session
        self._current_url = ""

    @property
    def url(self) -> str:
        """Get current URL."""
        return self._current_url

    @property
    def raw_session(self):
        """Get the raw Notte session for direct access."""
        return self._session

    async def goto(self, url: str, wait_until: str = 'domcontentloaded') -> None:
        """Navigate to a URL."""
        self._session.goto(url)
        self._current_url = url

    async def action(self, instruction: str) -> Any:
        """Execute a natural language action on the page."""
        print(f"[Notte] Executing action: {instruction}")
        result = self._session.act(instruction)
        return result

    async def content(self) -> str:
        """Get page HTML content."""
        result = self._session.scrape(scrape_links=True, only_main_content=False)
        return result.markdown if hasattr(result, 'markdown') else str(result)

    async def wait_for_timeout(self, timeout: int) -> None:
        """Wait for specified milliseconds."""
        import asyncio
        await asyncio.sleep(timeout / 1000)

    async def evaluate(self, script: str) -> Any:
        """Execute JavaScript - for scrolling, use Notte action."""
        if 'scrollTo' in script or 'scroll' in script.lower():
            self._session.act("scroll down the page")
        return None

    async def query_selector(self, selector: str) -> Optional['NotteElement']:
        """Query for an element - returns wrapper for Notte actions."""
        return NotteElement(self._session, selector)

    async def query_selector_all(self, selector: str) -> List['NotteElement']:
        """Query for all matching elements."""
        return [NotteElement(self._session, selector)]

    @property
    def keyboard(self) -> 'NotteKeyboard':
        """Get keyboard interface."""
        return NotteKeyboard(self._session)

    async def fill(self, selector: str, value: str) -> None:
        """Fill an input field using natural language."""
        self._session.act(f"type '{value}' into the {selector} field")

    async def click(self, selector: str) -> None:
        """Click an element using natural language."""
        self._session.act(f"click on {selector}")

    async def wait_for_selector(self, selector: str, state: str = 'visible', timeout: int = 10000) -> None:
        """Wait for element - Notte handles this automatically."""
        pass

    async def wait_for_load_state(self, state: str = 'networkidle', timeout: int = 10000) -> None:
        """Wait for load state - Notte handles this automatically."""
        import asyncio
        await asyncio.sleep(1)


class NotteElement:
    """Wrapper for element interactions."""

    def __init__(self, session, selector: str):
        self._session = session
        self._selector = selector

    async def click(self) -> None:
        """Click the element."""
        self._session.act(f"click on {self._selector}")

    async def fill(self, value: str) -> None:
        """Fill the element with text."""
        self._session.act(f"type '{value}' into {self._selector}")

    async def inner_text(self) -> str:
        """Get inner text - use scrape."""
        result = self._session.scrape(only_main_content=True)
        return result.markdown if hasattr(result, 'markdown') else str(result)

    async def text_content(self) -> Optional[str]:
        """Get text content."""
        return await self.inner_text()

    async def get_attribute(self, name: str) -> Optional[str]:
        """Get attribute value."""
        return None

    async def query_selector(self, selector: str) -> Optional['NotteElement']:
        """Query within element."""
        return NotteElement(self._session, f"{self._selector} {selector}")


class NotteKeyboard:
    """Keyboard interface for Notte."""

    def __init__(self, session):
        self._session = session

    async def type(self, text: str, delay: int = 0) -> None:
        """Type text."""
        self._session.act(f"type '{text}'")

    async def press(self, key: str) -> None:
        """Press a key."""
        self._session.act(f"press the {key} key")


class NotteContext:
    """Browser context wrapper for Notte."""

    def __init__(self, session):
        self._session = session

    async def storage_state(self, path: str) -> None:
        """Save storage state - get cookies from Notte."""
        try:
            cookies = self._session.get_cookies()
            import json
            with open(path, 'w') as f:
                json.dump({"cookies": cookies}, f)
        except Exception as e:
            print(f"Could not save storage state: {e}")


class BrowserManager:
    """
    Manages Notte browser sessions for web scraping.
    Provides Playwright-compatible interface for easy migration.
    """

    _instance: Optional['BrowserManager'] = None
    _client: Optional[NotteClient] = None

    def __init__(self):
        self.headless = os.getenv("HEADLESS", "true").lower() == "true"
        self.timeout = int(os.getenv("BROWSER_TIMEOUT", "30000"))
        self.api_key = os.getenv("NOTTE_API_KEY")

    @classmethod
    async def get_instance(cls) -> 'BrowserManager':
        """Get or create singleton instance."""
        if cls._instance is None:
            cls._instance = cls()
            await cls._instance._initialize()
        return cls._instance

    async def _initialize(self):
        """Initialize Notte client."""
        if self._client is None:
            self._client = NotteClient(api_key=self.api_key)
            print(f"[BrowserManager] Notte client initialized")

    async def close(self):
        """Close Notte client."""
        self._client = None
        BrowserManager._instance = None
        print(f"[BrowserManager] Notte client closed")

    @asynccontextmanager
    async def new_context(self, storage_state: Optional[str] = None):
        """
        Create a new Notte session with optional storage state.

        Args:
            storage_state: Path to storage state file for session persistence
        """
        if self._client is None:
            await self._initialize()

        # Create Notte session
        open_viewer = not self.headless
        session = self._client.Session(
            open_viewer=open_viewer,
            timeout_minutes=10,
            browser_type='chrome-nightly',  # Required for solve_captchas (options: firefox, chrome-nightly)
            solve_captchas=True,
        )

        # Start the session
        session.__enter__()

        # Load cookies if storage state exists
        if storage_state and os.path.exists(storage_state):
            try:
                import json
                with open(storage_state, 'r') as f:
                    state = json.load(f)
                    if 'cookies' in state:
                        session.set_cookies(cookies=state['cookies'])
            except Exception as e:
                print(f"Could not load storage state: {e}")

        context = NotteContext(session)

        try:
            yield context, session
        finally:
            try:
                session.__exit__(None, None, None)
            except Exception as e:
                print(f"Error closing session: {e}")

    @asynccontextmanager
    async def new_page(self, context_and_session=None):
        """
        Create a new page wrapper.

        Args:
            context_and_session: Tuple of (context, session) from new_context
        """
        if context_and_session:
            context, session = context_and_session
            page = NotteSession(session)
            try:
                yield page
            finally:
                pass
        else:
            async with self.new_context() as (ctx, session):
                page = NotteSession(session)
                try:
                    yield page
                finally:
                    pass

    async def save_storage_state(self, context: NotteContext, path: str):
        """Save browser context storage state (cookies) to file."""
        await context.storage_state(path=path)

    @staticmethod
    async def wait_for_navigation(page: NotteSession, timeout: int = 30000):
        """Wait for navigation to complete."""
        import asyncio
        await asyncio.sleep(2)

    @staticmethod
    async def safe_click(page: NotteSession, selector: str, timeout: int = 10000):
        """Safely click an element."""
        await page.click(selector)

    @staticmethod
    async def safe_fill(page: NotteSession, selector: str, value: str, timeout: int = 10000):
        """Safely fill an input field."""
        await page.fill(selector, value)

    @staticmethod
    async def safe_get_text(page: NotteSession, selector: str, timeout: int = 5000) -> Optional[str]:
        """Safely get text content from an element."""
        try:
            element = await page.query_selector(selector)
            if element:
                return await element.text_content()
        except Exception:
            pass
        return None

    @staticmethod
    async def safe_get_attribute(page: NotteSession, selector: str, attribute: str, timeout: int = 5000) -> Optional[str]:
        """Safely get an attribute from an element."""
        try:
            element = await page.query_selector(selector)
            if element:
                return await element.get_attribute(attribute)
        except Exception:
            pass
        return None

    def get_agent(self, session, task: str, max_steps: int = 30):
        """
        Get a Notte AI agent for natural language tasks.

        Args:
            session: Notte session
            task: Natural language task description
            max_steps: Maximum steps for the agent
        """
        return self._client.Agent(
            session=session,
            reasoning_model='gemini/gemini-2.5-flash',
            max_steps=max_steps
        )


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
