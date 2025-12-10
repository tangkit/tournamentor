import os
from typing import Optional, Any, Dict, List
from contextlib import asynccontextmanager
from notte_sdk import NotteClient


class NotteSession:
    """Wrapper around Notte session for page interactions."""

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
        """Navigate to a URL using Notte execute method."""
        print(f"[Notte] goto: Navigating to {url}")
        try:
            # Notte uses execute with action type 'goto'
            result = self._session.execute({"type": "goto", "url": url})
            self._current_url = url
            print(f"[Notte] goto: Navigation completed")
            if result:
                print(f"[Notte] goto: Result: {result}")
        except Exception as e:
            print(f"[Notte] goto: Navigation failed: {e}")
            raise

    async def action(self, instruction: str) -> Any:
        """Execute a natural language action on the page using Notte observe/execute."""
        print(f"[Notte] action: Executing '{instruction}'")
        try:
            # Observe available actions on the page
            observation = self._session.observe()
            print(f"[Notte] action: observe() returned {type(observation).__name__}")

            # Debug: show observation structure
            if hasattr(observation, '__dict__'):
                print(f"[Notte] action: observation attrs: {list(observation.__dict__.keys())}")

            # Get available actions
            actions = None
            if hasattr(observation, 'space') and hasattr(observation.space, 'actions'):
                actions = observation.space.actions
                print(f"[Notte] action: Found {len(actions)} actions in observation.space.actions")
            elif hasattr(observation, 'actions'):
                actions = observation.actions
                print(f"[Notte] action: Found {len(actions)} actions in observation.actions")

            if actions:
                # Show first few actions for debugging
                print(f"[Notte] action: Sample actions:")
                for i, act in enumerate(actions[:5]):
                    print(f"[Notte]   {i}: {act}")
                    if hasattr(act, '__dict__'):
                        print(f"[Notte]      attrs: {act.__dict__}")

                # Try to find matching action
                instruction_lower = instruction.lower()
                keywords = [w for w in instruction_lower.split() if len(w) > 2]

                for act in actions:
                    # Check action description/text
                    act_str = str(act).lower()
                    act_desc = getattr(act, 'description', '').lower() if hasattr(act, 'description') else ''
                    act_text = getattr(act, 'text', '').lower() if hasattr(act, 'text') else ''

                    combined = f"{act_str} {act_desc} {act_text}"

                    # Match on keywords
                    if any(kw in combined for kw in keywords):
                        print(f"[Notte] action: Found matching action: {act}")
                        result = self._session.execute(act)
                        print(f"[Notte] action: execute() completed")
                        return result

                print(f"[Notte] action: No match found for keywords: {keywords}")
            else:
                print(f"[Notte] action: No actions available in observation")

            return None
        except Exception as e:
            print(f"[Notte] action: FAILED - {e}")
            import traceback
            traceback.print_exc()
            raise

    async def content(self) -> str:
        """Get page content (HTML or markdown depending on what's available)."""
        print(f"[Notte] content: Fetching page content...")
        try:
            result = self._session.scrape(scrape_links=True, only_main_content=False)
            print(f"[Notte] content: Scrape result type={type(result).__name__}")

            # Debug: Show all available attributes
            if hasattr(result, '__dict__'):
                print(f"[Notte] content: Result attributes: {list(result.__dict__.keys())}")
            else:
                print(f"[Notte] content: Result dir: {[a for a in dir(result) if not a.startswith('_')]}")

            # Try to get HTML first, fall back to markdown
            if hasattr(result, 'html') and result.html:
                print(f"[Notte] content: Found HTML (length={len(result.html)})")
                return result.html
            elif hasattr(result, 'page_html') and result.page_html:
                print(f"[Notte] content: Found page_html (length={len(result.page_html)})")
                return result.page_html
            elif hasattr(result, 'raw_html') and result.raw_html:
                print(f"[Notte] content: Found raw_html (length={len(result.raw_html)})")
                return result.raw_html
            elif hasattr(result, 'markdown') and result.markdown:
                content = result.markdown
                print(f"[Notte] content: Found markdown (length={len(content)})")
                # Show first 500 chars for debugging
                print(f"[Notte] content: Preview: {content[:500] if len(content) > 500 else content}")
                return content
            elif hasattr(result, 'text') and result.text:
                content = result.text
                print(f"[Notte] content: Found text (length={len(content)})")
                return content
            else:
                content = str(result)
                print(f"[Notte] content: Using str(result) (length={len(content)})")
                print(f"[Notte] content: Preview: {content[:500] if len(content) > 500 else content}")
                return content
        except Exception as e:
            print(f"[Notte] content: FAILED - {e}")
            import traceback
            traceback.print_exc()
            return ""

    async def wait_for_timeout(self, timeout: int) -> None:
        """Wait for specified milliseconds."""
        import asyncio
        print(f"[Notte] wait: {timeout}ms")
        await asyncio.sleep(timeout / 1000)

    async def evaluate(self, script: str) -> Any:
        """Execute JavaScript - for scrolling, use Notte scroll_down action."""
        if 'scrollTo' in script or 'scroll' in script.lower():
            print(f"[Notte] evaluate: Executing scroll_down")
            try:
                self._session.execute({"type": "scroll_down"})
                print(f"[Notte] evaluate: scroll_down completed")
            except Exception as e:
                print(f"[Notte] evaluate: scroll_down FAILED - {e}")
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
        instruction = f"type '{value}' into the {selector} field"
        print(f"[Notte] fill: {instruction}")
        if hasattr(self._session, 'step'):
            self._session.step(instruction)
        else:
            await self.action(instruction)

    async def click(self, selector: str) -> None:
        """Click an element using natural language."""
        instruction = f"click on {selector}"
        print(f"[Notte] click: {instruction}")
        if hasattr(self._session, 'step'):
            self._session.step(instruction)
        else:
            await self.action(instruction)

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

    def _get_actions(self):
        """Get available actions from observe()."""
        observation = self._session.observe()
        if hasattr(observation, 'space') and hasattr(observation.space, 'actions'):
            return observation.space.actions
        elif hasattr(observation, 'actions'):
            return observation.actions
        return []

    async def click(self) -> None:
        """Click the element using observe/execute pattern."""
        print(f"[NotteElement] click: Looking for '{self._selector}'")
        actions = self._get_actions()
        print(f"[NotteElement] click: Found {len(actions)} available actions")

        selector_lower = self._selector.lower()
        keywords = [w for w in selector_lower.split() if len(w) > 2]

        for act in actions:
            act_type = getattr(act, 'type', '').lower()
            act_str = str(act).lower()
            act_desc = getattr(act, 'description', '').lower() if hasattr(act, 'description') else ''

            # Look for click actions that match our selector
            if 'click' in act_type or 'click' in act_str:
                if any(kw in f"{act_str} {act_desc}" for kw in keywords):
                    print(f"[NotteElement] click: Executing {act}")
                    self._session.execute(act)
                    return

        # If no specific match, try first click action on input-like elements
        for act in actions:
            act_type = getattr(act, 'type', '').lower()
            act_str = str(act).lower()
            if 'click' in act_type and ('input' in act_str or 'text' in act_str or 'search' in act_str):
                print(f"[NotteElement] click: Using fallback input click: {act}")
                self._session.execute(act)
                return

        print(f"[NotteElement] click: No matching action found for '{self._selector}'")

    async def fill(self, value: str) -> None:
        """Fill the element with text using observe/execute pattern."""
        print(f"[NotteElement] fill: Looking for '{self._selector}' to fill with '{value}'")
        actions = self._get_actions()
        print(f"[NotteElement] fill: Found {len(actions)} available actions")

        selector_lower = self._selector.lower()
        keywords = [w for w in selector_lower.split() if len(w) > 2]

        for act in actions:
            act_type = getattr(act, 'type', '').lower()
            act_str = str(act).lower()
            act_desc = getattr(act, 'description', '').lower() if hasattr(act, 'description') else ''

            # Look for fill/type actions that match our selector
            if 'fill' in act_type or 'type' in act_type:
                if any(kw in f"{act_str} {act_desc}" for kw in keywords):
                    # Modify action to include the value
                    if hasattr(act, 'value'):
                        act.value = value
                    print(f"[NotteElement] fill: Executing {act}")
                    self._session.execute(act)
                    return

        # If no specific match, look for any fill action on input elements
        for act in actions:
            act_type = getattr(act, 'type', '').lower()
            act_str = str(act).lower()
            if 'fill' in act_type and ('input' in act_str or 'text' in act_str or 'search' in act_str):
                if hasattr(act, 'value'):
                    act.value = value
                print(f"[NotteElement] fill: Using fallback input fill: {act}")
                self._session.execute(act)
                return

        print(f"[NotteElement] fill: No matching action found for '{self._selector}'")

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
        instruction = f"type '{text}'"
        print(f"[NotteKeyboard] type: {instruction}")
        if hasattr(self._session, 'step'):
            self._session.step(instruction)
        else:
            # Use execute with press_key for each character as fallback
            for char in text:
                self._session.execute({"type": "press_key", "key": char})

    async def press(self, key: str) -> None:
        """Press a key."""
        print(f"[NotteKeyboard] press: {key}")
        # Use the press_key action type directly
        self._session.execute({"type": "press_key", "key": key})


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
    """Manages Notte AI browser sessions for web scraping."""

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
        # Enable open_viewer for debugging (controlled by HEADLESS env var)
        open_viewer = not self.headless
        print(f"[BrowserManager] Creating session (headless=True, open_viewer={open_viewer})...")
        session = self._client.Session(
            headless=True,  # Notte cloud only supports headless mode
            open_viewer=open_viewer,  # Opens browser viewer for debugging
            timeout_minutes=15,
            browser_type='chrome-nightly',  # Required for solve_captchas
            proxies=True,  # Required when using chrome-nightly with solve_captchas
            solve_captchas=True,
        )

        session_closed = False
        try:
            # Start the session using context manager
            print(f"[BrowserManager] Starting session...")
            session.__enter__()
            print(f"[BrowserManager] Session started successfully (ID: {getattr(session, 'session_id', 'unknown')})")

            # Debug: Show available methods on the session object
            session_methods = [m for m in dir(session) if not m.startswith('_')]
            print(f"[BrowserManager] Session type: {type(session).__name__}")
            print(f"[BrowserManager] Session methods: {session_methods}")

            # Load cookies if storage state exists
            if storage_state and os.path.exists(storage_state):
                try:
                    import json
                    with open(storage_state, 'r') as f:
                        state = json.load(f)
                        if 'cookies' in state:
                            session.set_cookies(cookies=state['cookies'])
                            print(f"[BrowserManager] Loaded cookies from storage state")
                except Exception as e:
                    print(f"[BrowserManager] Could not load storage state: {e}")

            context = NotteContext(session)
            yield context, session

        except Exception as e:
            print(f"[BrowserManager] Session error: {e}")
            # Try to close the session even if it failed to start fully
            self._force_close_session(session)
            session_closed = True
            raise

        finally:
            # Close the session if not already closed
            if not session_closed:
                self._force_close_session(session)

    def _force_close_session(self, session):
        """Force close a session, trying multiple methods."""
        # Try to get session_id - Notte SDK raises ValueError if session wasn't started
        try:
            session_id = session.session_id
        except (ValueError, AttributeError):
            # Session was never started, nothing to close
            print(f"[BrowserManager] Session was not started, nothing to close")
            return

        if not session_id:
            return

        print(f"[BrowserManager] Closing session {session_id}...")

        # Try normal exit first
        try:
            session.__exit__(None, None, None)
            print(f"[BrowserManager] Session {session_id} closed via __exit__")
            return
        except Exception as e:
            print(f"[BrowserManager] __exit__ failed: {e}")

        # Try stopping via client
        try:
            if self._client:
                self._client.stop(session_id=session_id)
                print(f"[BrowserManager] Session {session_id} force stopped via client.stop()")
                return
        except Exception as e:
            print(f"[BrowserManager] client.stop() failed: {e}")

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
