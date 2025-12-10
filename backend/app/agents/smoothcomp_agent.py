import re
from typing import List, Optional
from datetime import datetime, timedelta
from bs4 import BeautifulSoup

from .base_agent import BaseTournamentAgent
from ..models import Tournament, TournamentSource
from ..browser.manager import BrowserManager, NotteSession, NotteContext


class SmoothcompAgent(BaseTournamentAgent):
    """
    A tournament scraping agent specifically for Smoothcomp.

    This class uses the BaseTournamentAgent "template" and fills in
    Smoothcomp-specific details:
      - Where to find events.
      - How to (optionally) log in.
      - How to apply filters.
      - How to parse the event detail pages.

    Notte AI is used under the hood to control the browser and read the page.
    """

    # ---- Basic properties that tell the base class who we are ----

    @property
    def source(self) -> TournamentSource:
        """
        Identify this agent's source as 'SMOOTHCOMP'.

        This is used for:
          - Logging.
          - Generating IDs.
          - Source field in Tournament model.
        """
        return TournamentSource.SMOOTHCOMP

    @property
    def base_url(self) -> str:
        """Base URL for Smoothcomp's website."""
        return "https://smoothcomp.com"

    @property
    def events_url(self) -> str:
        """URL for Smoothcomp's upcoming events listing."""
        return "https://smoothcomp.com/en/events/upcoming"

    @property
    def login_url(self) -> str:
        """URL for Smoothcomp's login page."""
        return "https://smoothcomp.com/en/login"

    @property
    def email_env_var(self) -> str:
        """Environment variable where Smoothcomp email is stored."""
        return "SMOOTHCOMP_EMAIL"

    @property
    def password_env_var(self) -> str:
        """Environment variable where Smoothcomp password is stored."""
        return "SMOOTHCOMP_PASSWORD"

    @property
    def requires_login(self) -> bool:
        """
        Override the default to say:
        Smoothcomp events page is PUBLIC, so we don't need to log in.

        If we wanted to scrape something that needs login (e.g. registrations),
        we could set this back to True.
        """
        return False

    # ---- LOGIN STATUS CHECK (required by BaseTournamentAgent) ----

    async def _check_logged_in(self, page: NotteSession) -> bool:
        """
        Check if we are already logged in to Smoothcomp.

        Even though events are public, we implement this because the
        BaseTournamentAgent expects it.

        The logic:
          1. Go to Smoothcomp home page.
          2. Look for typical "logged-in" elements like profile icons, logout links, etc.
          3. If found, return True; otherwise, False.
        """
        try:
            # Navigate to Smoothcomp base URL and wait for DOM.
            await page.goto(self.base_url, wait_until='domcontentloaded')
            await page.wait_for_timeout(2000)  # Short delay to make sure page is stable.

            # These are CSS selectors that might only appear when a user is logged in.
            logged_in_selectors = [
                '[data-testid="user-menu"]',
                '.user-dropdown',
                '.profile-menu',
                'a[href*="/profile"]',
                'a[href*="/logout"]',
                '.nav-user',
            ]

            # If we find any of these selectors on the page, assume the user is logged in.
            for selector in logged_in_selectors:
                element = await page.query_selector(selector)
                if element:
                    return True

            # If we see a login button/link, it's likely that we're NOT logged in.
            login_button = await page.query_selector('a[href*="/login"]')
            if login_button:
                return False

            # Fallback: if we couldn't confidently detect either state, assume not logged in.
            return False
        except Exception as e:
            print(f"Error checking login status: {e}")
            return False

    # ---- LOGIN IMPLEMENTATION (not really used because requires_login=False) ----

    async def _login(self, page: NotteSession, context: NotteContext) -> bool:
        """
        Try to log in to Smoothcomp.

        Steps:
          1. Get email & password from environment.
          2. Go to login page.
          3. Fill email and password into the form.
          4. Click the login button.
          5. Wait for navigation.
          6. Check if login succeeded.
          7. Save session state if success.

        Note: For this particular agent, events don't require login, but this
        function is here in case we want to use it for other private pages.
        """
        email, password = self.get_credentials()
        if not email or not password:
            # If we don't have credentials, we can't log in.
            return False

        try:
            # Go to the login page and wait for it to load.
            await page.goto(self.login_url, wait_until='domcontentloaded')
            await page.wait_for_timeout(2000)

            # Possible selectors for the email input field.
            email_selectors = [
                'input[name="email"]',
                'input[type="email"]',
                '#email',
                'input[placeholder*="email" i]',
            ]

            # Possible selectors for the password input field.
            password_selectors = [
                'input[name="password"]',
                'input[type="password"]',
                '#password',
            ]

            # Try each email selector until one works.
            for selector in email_selectors:
                try:
                    await page.wait_for_selector(selector, timeout=5000)
                    await page.fill(selector, email)
                    break
                except Exception:
                    # If this selector didn't work, move to the next one.
                    continue

            # Try each password selector until one works.
            for selector in password_selectors:
                try:
                    await page.wait_for_selector(selector, timeout=5000)
                    await page.fill(selector, password)
                    break
                except Exception:
                    continue

            # Try clicking various types of "submit" buttons (login, sign in, etc.).
            submit_selectors = [
                'button[type="submit"]',
                'input[type="submit"]',
                'button:has-text("Log in")',
                'button:has-text("Sign in")',
                'button:has-text("Login")',
            ]

            for selector in submit_selectors:
                try:
                    await page.click(selector)
                    break
                except Exception:
                    continue

            # Wait a bit for the login to complete and network to settle down.
            await page.wait_for_timeout(3000)
            await page.wait_for_load_state('networkidle', timeout=10000)

            # Re-check if we are logged in now.
            logged_in = await self._check_logged_in(page)
            if logged_in:
                # If login succeeded, save session cookies/state for the future.
                await self._save_session(context)
                return True

            return False

        except Exception as e:
            print(f"Login error: {e}")
            return False

    # ---- HANDLE COOKIE POPUP ----

    async def _handle_cookie_popup(self, page: NotteSession) -> None:
        """
        Some websites show a cookie consent popup asking you to accept cookies.

        This function tries to:
          - Wait a bit for the popup to appear.
          - Use Notte's "observe" API to find an "Accept" button.
          - Click on it.
          - If nothing is found, quietly give up.

        It's written to be robust and not crash if the popup isn't there.
        """
        try:
            print("[Smoothcomp] === HANDLING COOKIE POPUP ===")
            print("[Smoothcomp] Waiting 5 seconds for page to settle (free plan rate limit)...")
            await page.wait_for_timeout(5000)

            # Try a few times in case the popup appears slowly.
            for attempt in range(3):
                print(f"[Smoothcomp] Attempt {attempt+1}: Looking for Accept button...")

                # Ask Notte: "What actions (clicks, fills, etc.) are currently available?"
                observation = page.raw_session.observe()
                actions = []

                # Normalize how we access the 'actions' list (depends on Notte's structure).
                if hasattr(observation, 'space') and hasattr(observation.space, 'actions'):
                    actions = observation.space.actions
                elif hasattr(observation, 'actions'):
                    actions = observation.actions

                # Now, among all available actions, try to find one that:
                #   - is a click action
                #   - has "accept" in its text label
                #   - DOES NOT contain "decline" (to avoid the wrong button).
                accept_action = None
                for act in actions:
                    act_label = getattr(act, 'text_label', '').lower() if hasattr(act, 'text_label') else ''
                    act_desc = getattr(act, 'description', '').lower() if hasattr(act, 'description') else ''
                    act_type = getattr(act, 'type', '').lower()

                    if act_type == 'click' and 'accept' in act_label and 'decline' not in act_label:
                        accept_action = act
                        print(f"[Smoothcomp] Found Accept button: {act}")
                        break

                if accept_action:
                    try:
                        # Tell Notte to execute this click action.
                        page.raw_session.execute(accept_action)
                        print("[Smoothcomp] Cookie Accept button clicked!")
                        await page.wait_for_timeout(3000)  # Wait for popup to disappear.
                        return
                    except Exception as e:
                        print(f"[Smoothcomp] Click failed: {e}, retrying...")
                        await page.wait_for_timeout(3000)
                else:
                    print("[Smoothcomp] Accept button not found in this attempt")
                    await page.wait_for_timeout(1000)

            print("[Smoothcomp] Cookie popup may not be present or already handled")

        except Exception as e:
            print(f"[Smoothcomp] Cookie popup handling failed or not present: {e}")
            import traceback
            traceback.print_exc()

    # ---- APPLY COUNTRY FILTER ----

    async def _apply_country_filter(self, page: NotteSession, location: str) -> bool:
        """
        Apply the 'Countries' filter on Smoothcomp's events page.

        The 'location' parameter can be:
          - A single country: "Malaysia"
          - Multiple countries separated by commas: "Malaysia,Taiwan"

        We:
          1. Split the string into a list of country names.
          2. For each country:
             a. Find and click on the Countries input field.
             b. Type the country name using keyboard.
             c. Wait for dropdown suggestions.
             d. Try to click on the correct suggestion.
             e. If that fails, use keyboard arrows to select it.
        """
        try:
            # Turn "Malaysia,Taiwan" into ["Malaysia", "Taiwan"]
            countries = [c.strip() for c in location.split(',') if c.strip()]
            print(f"[Smoothcomp] === APPLYING COUNTRY FILTER ===")
            print(f"[Smoothcomp] Countries to filter: {countries}")

            # Wait for page UI to fully load (especially on free Notte plan).
            await page.wait_for_timeout(3000)

            # Process each country one by one.
            for i, country in enumerate(countries):
                print(f"\n[Smoothcomp] --- Adding country {i+1}/{len(countries)}: '{country}' ---")
                try:
                    # Step 1: Find the Countries input field via Notte actions.
                    print(f"[Smoothcomp] Step 1: Looking for Countries input field...")
                    observation = page.raw_session.observe()

                    actions = []
                    if hasattr(observation, 'space') and hasattr(observation.space, 'actions'):
                        actions = observation.space.actions
                    elif hasattr(observation, 'actions'):
                        actions = observation.actions

                    print(f"[Smoothcomp] Found available actions: {actions}")

                    countries_input_action = None
                    for act in actions:
                        act_str = str(act).lower()
                        act_desc = getattr(act, 'description', '').lower() if hasattr(act, 'description') else ''
                        combined = f"{act_str} {act_desc}"

                        # Look for an action that seems related to "Countries" and could be fill/click/input/select.
                        if 'countr' in combined and ('click' in combined or 'fill' in combined or 'input' in combined or 'select' in combined):
                            countries_input_action = act
                            print(f"[Smoothcomp] Found Countries action: {act}")
                            break

                    if countries_input_action:
                        # Click on the country input field.
                        print(f"[Smoothcomp] Clicking Countries input...")
                        page.raw_session.execute(countries_input_action)
                        await page.wait_for_timeout(500)
                    else:
                        # If Notte can't find the action, try a natural language command as fallback.
                        print(f"[Smoothcomp] Countries input not found in actions, trying fallback...")
                        await page.action("click on Select countries")
                        await page.wait_for_timeout(500)

                    # Step 2: Type the country name into the input field using keyboard.
                    print(f"[Smoothcomp] Step 2: Typing '{country}' using keyboard...")
                    keyboard = page.keyboard
                    await keyboard.type(country)
                    await page.wait_for_timeout(1500)  # Wait for suggestions dropdown.

                    # Step 3: Look for the country name in the dropdown suggestions.
                    print(f"[Smoothcomp] Step 3: Looking for '{country}' in dropdown to click...")
                    observation = page.raw_session.observe()
                    actions = []
                    if hasattr(observation, 'space') and hasattr(observation.space, 'actions'):
                        actions = observation.space.actions
                    elif hasattr(observation, 'actions'):
                        actions = observation.actions

                    country_lower = country.lower()
                    country_action = None
                    for act in actions:
                        act_label = getattr(act, 'text_label', '') if hasattr(act, 'text_label') else ''
                        act_type = getattr(act, 'type', '').lower()

                        if act_type == 'click' and country_lower in act_label.lower():
                            country_action = act
                            print(f"[Smoothcomp] Found '{country}' in dropdown: {act}")
                            break

                    if country_action:
                        # Click on the correct dropdown option.
                        page.raw_session.execute(country_action)
                        print(f"[Smoothcomp] Clicked on '{country}' in dropdown")
                    else:
                        # Fallback: use arrow keys and Enter to select an option.
                        print(f"[Smoothcomp] Country not found in dropdown, trying keyboard fallback...")
                        await keyboard.press("ArrowDown")
                        await page.wait_for_timeout(300)
                        await keyboard.press("Enter")

                    await page.wait_for_timeout(1000)
                    print(f"[Smoothcomp] Successfully added country: {country}")

                except Exception as e:
                    print(f"[Smoothcomp] ERROR adding country '{country}': {e}")
                    import traceback
                    traceback.print_exc()
                    # If one country fails, continue with the next.
                    continue

            print(f"\n[Smoothcomp] Country filter completed for: {countries}")
            return True

        except Exception as e:
            print(f"[Smoothcomp] Country filter error: {e}")
            import traceback
            traceback.print_exc()
            return False

    # ---- DATE FILTER (CURRENTLY NOT USED RELIABLY VIA UI) ----
    # I'll keep comments mid-level here because it's long and mostly experimental.

    async def _apply_date_filter(self, page: NotteSession, date_from: str, date_to: str) -> bool:
<<<<<<< HEAD
        """Apply date filter on Smoothcomp events page using Notte Agent.

        Uses the Notte AI Agent with reasoning capabilities to:
        1. Find and click on date input fields
        2. Navigate calendar picker to correct month/year
        3. Select the target date
=======
        """
        Attempt to apply date filters using Smoothcomp's calendar UI.

        In theory:
          - Click "Start date" field, pick date_from.
          - Click "End date" field, pick date_to.
        In practice:
          - This is tricky with Notte free plan, so date filtering is
            often done AFTER scraping via Python code instead.
>>>>>>> 07d2f1d (Updated the date filter to click)

        The logic inside uses:
          - Nested helper functions to:
            * click the date fields,
            * navigate months in the popup calendar,
            * click specific days,
            * or type dates directly.
        """
        try:
            print(f"[Smoothcomp] === APPLYING DATE FILTER (Notte Agent) ===")
            print(f"[Smoothcomp] Date range: {date_from} to {date_to}")

<<<<<<< HEAD
            # Wait for page to settle
            await page.wait_for_timeout(3000)

            # Get the raw Notte session and browser manager
            from ..browser.manager import get_browser_manager
            browser_manager = await get_browser_manager()
            raw_session = page.raw_session

            # Parse dates for the agent task
            from datetime import datetime
=======
            # Let the page fully settle first.
            await page.wait_for_timeout(5000)

            # Scroll to top to ensure filter area is visible.
            await page.evaluate('window.scrollTo(0, 0)')
            await page.wait_for_timeout(500)

            # Helper to parse "YYYY-MM-DD" into (year, month, day) integers.
            def parse_date(date_str: str) -> tuple:
                parts = date_str.split('-')
                return int(parts[0]), int(parts[1]), int(parts[2])

            # Month names used to detect what month the calendar is showing.
>>>>>>> 07d2f1d (Updated the date filter to click)
            month_names = ['January', 'February', 'March', 'April', 'May', 'June',
                           'July', 'August', 'September', 'October', 'November', 'December']

<<<<<<< HEAD
            def format_date_for_agent(date_str: str) -> str:
                """Convert YYYY-MM-DD to human-readable format for agent."""
                parts = date_str.split('-')
                year, month, day = int(parts[0]), int(parts[1]), int(parts[2])
                return f"{month_names[month-1]} {day}, {year}"

            # Apply start date using agent
=======
            async def click_date_field(field_name: str) -> bool:
                """
                Try to click on the 'Start date' or 'End date' input.

                Uses Notte's observe() to find actions related to date fields.
                As a fallback, uses a natural language action.
                """
                full_label = f"{field_name} date".lower()
                print(f"[Smoothcomp] Looking for full_label '{full_label}' field_name...")

                observation = page.raw_session.observe()
                actions = []
                if hasattr(observation, 'space') and hasattr(observation.space, 'actions'):
                    actions = observation.space.actions
                elif hasattr(observation, 'actions'):
                    actions = observation.actions

                # First pass: look for actions whose label/description contain "start date" or "end date".
                for act in actions:
                    act_desc = getattr(act, 'description', '').lower() if hasattr(act, 'description') else ''
                    act_label = getattr(act, 'text_label', '').lower() if hasattr(act, 'text_label') else ''
                    act_type = getattr(act, 'type', '').lower()

                    # Skip links (these often have 'href=' and aren't inputs).
                    if 'href=' in act_desc:
                        continue

                    if full_label in act_label or full_label in act_desc:
                        print(f"[Smoothcomp] Found '{full_label}' field: {act}")
                        page.raw_session.execute(act)
                        return True

                # Second pass: look for fill actions involving dates.
                for act in actions:
                    act_desc = getattr(act, 'description', '').lower() if hasattr(act, 'description') else ''
                    act_label = getattr(act, 'text_label', '').lower() if hasattr(act, 'text_label') else ''
                    act_type = getattr(act, 'type', '').lower()

                    if 'href=' in act_desc:
                        continue

                    if act_type == 'fill' and 'date' in act_label:
                        print(f"[Smoothcomp] Found date input (fill): {act}")
                        page.raw_session.execute(act)
                        return True

                # Third pass: look at CSS selectors for date-related classes.
                for act in actions:
                    act_desc = getattr(act, 'description', '').lower() if hasattr(act, 'description') else ''
                    act_type = getattr(act, 'type', '').lower()
                    selector = getattr(act, 'selector', None)

                    if 'href=' in act_desc:
                        continue

                    if selector:
                        css = getattr(selector, 'css_selector', '').lower() if hasattr(selector, 'css_selector') else ''
                        if 'date' in css or 'picker' in css or 'calendar' in css:
                            print(f"[Smoothcomp] Found date element by selector: {act}")
                            page.raw_session.execute(act)
                            return True

                # Fallback: try natural language click.
                print(f"[Smoothcomp] Using natural language to click '{full_label}' field...")
                try:
                    if field_name == "start":
                        await page.action("click on Start date")
                    else:
                        await page.action("click on End date")
                    await page.wait_for_timeout(1000)
                    return True
                except Exception as e:
                    print(f"[Smoothcomp] Natural language click failed: {e}")

                # Debugging info if we fail.
                print(f"[Smoothcomp] Could not find '{full_label}' field")
                print(f"[Smoothcomp] Available actions ({len(actions)} total):")
                fill_actions = [a for a in actions if getattr(a, 'type', '').lower() == 'fill']
                print(f"[Smoothcomp] Fill actions: {len(fill_actions)}")
                for i, act in enumerate(fill_actions[:5]):
                    act_label = getattr(act, 'text_label', '') if hasattr(act, 'text_label') else ''
                    act_desc = getattr(act, 'description', '')[:80] if hasattr(act, 'description') else ''
                    print(f"[Smoothcomp]   fill {i}: label='{act_label}', desc='{act_desc}'")
                return False

            async def navigate_to_month_year(target_year: int, target_month: int) -> bool:
                """
                Try to move the calendar popup to show a specific (year, month).

                It:
                  - Observes the calendar header text (like "January 2026").
                  - If current month/year is before the target, clicks 'next'.
                  - If it's after, clicks 'prev'.
                  - Repeats up to a limit.
                """
                print(f"[Smoothcomp] Navigating to {month_names[target_month-1]} {target_year}...")

                max_nav_attempts = 24  # Up to ~2 years forward/backward.
                for _ in range(max_nav_attempts):
                    await page.wait_for_timeout(500)

                    observation = page.raw_session.observe()
                    actions = []
                    if hasattr(observation, 'space') and hasattr(observation.space, 'actions'):
                        actions = observation.space.actions
                    elif hasattr(observation, 'actions'):
                        actions = observation.actions

                    current_month = None
                    current_year = None

                    # Try to detect current calendar header like "January 2026"
                    for act in actions:
                        act_label = getattr(act, 'text_label', '') if hasattr(act, 'text_label') else ''
                        for i, month_name in enumerate(month_names):
                            if month_name in act_label:
                                import re
                                year_match = re.search(r'(\d{4})', act_label)
                                if year_match:
                                    current_month = i + 1
                                    current_year = int(year_match.group(1))
                                    print(f"[Smoothcomp] Calendar shows: {month_name} {current_year}")
                                    break
                        if current_month:
                            break

                    if current_month and current_year:
                        # Convert (year, month) to a single number to compare positions.
                        current_total = current_year * 12 + current_month
                        target_total = target_year * 12 + target_month

                        if current_total == target_total:
                            print(f"[Smoothcomp] Reached target month/year!")
                            return True

                        # Decide direction: need to go forward or backward?
                        if target_total > current_total:
                            # Go forward (next month)
                            nav_action = None
                            for act in actions:
                                act_label = getattr(act, 'text_label', '').lower() if hasattr(act, 'text_label') else ''
                                act_desc = getattr(act, 'description', '').lower() if hasattr(act, 'description') else ''
                                act_type = getattr(act, 'type', '').lower()
                                if act_type == 'click' and ('next' in act_label or 'next' in act_desc or '>' in act_label or 'forward' in act_desc):
                                    nav_action = act
                                    break
                            if nav_action:
                                print(f"[Smoothcomp] Clicking next month...")
                                page.raw_session.execute(nav_action)
                            else:
                                await page.keyboard.press("ArrowRight")
                        else:
                            # Go backward (previous month)
                            nav_action = None
                            for act in actions:
                                act_label = getattr(act, 'text_label', '').lower() if hasattr(act, 'text_label') else ''
                                act_desc = getattr(act, 'description', '').lower() if hasattr(act, 'description') else ''
                                act_type = getattr(act, 'type', '').lower()
                                if act_type == 'click' and ('prev' in act_label or 'prev' in act_desc or '<' in act_label or 'back' in act_desc):
                                    nav_action = act
                                    break
                            if nav_action:
                                print(f"[Smoothcomp] Clicking previous month...")
                                page.raw_session.execute(nav_action)
                            else:
                                await page.keyboard.press("ArrowLeft")
                    else:
                        # If we can't detect current month/year, try clicking a 'next' action blindly.
                        print(f"[Smoothcomp] Cannot determine current calendar position, trying to navigate...")
                        for act in actions:
                            act_type = getattr(act, 'type', '').lower()
                            act_label = getattr(act, 'text_label', '').lower() if hasattr(act, 'text_label') else ''
                            if act_type == 'click' and ('next' in act_label or '>' in act_label):
                                page.raw_session.execute(act)
                                break

                print(f"[Smoothcomp] Could not navigate to target month/year after max attempts")
                return False

            async def click_day(day: int) -> bool:
                """
                Click a specific day number (e.g., 10) in the calendar popup.
                """
                print(f"[Smoothcomp] Looking for day {day} to click...")
                await page.wait_for_timeout(500)

                observation = page.raw_session.observe()
                actions = []
                if hasattr(observation, 'space') and hasattr(observation.space, 'actions'):
                    actions = observation.space.actions
                elif hasattr(observation, 'actions'):
                    actions = observation.actions

                day_str = str(day)
                for act in actions:
                    act_label = getattr(act, 'text_label', '') if hasattr(act, 'text_label') else ''
                    act_type = getattr(act, 'type', '').lower()

                    # Use exact match to avoid "1" matching "11" etc.
                    if act_type == 'click' and act_label.strip() == day_str:
                        print(f"[Smoothcomp] Found day {day}: {act}")
                        page.raw_session.execute(act)
                        return True

                print(f"[Smoothcomp] Could not find day {day} in calendar")
                return False

            async def select_date(date_str: str, field_name: str) -> bool:
                """
                This approach types the date directly into the field instead of
                fully driving the calendar with clicks.

                Steps:
                  1. Click the 'start' or 'end' date field.
                  2. Select all and delete existing contents.
                  3. Type the date string (YYYY-MM-DD).
                  4. Press Tab to confirm.
                """
                if not date_str:
                    return True

                print(f"[Smoothcomp] Selecting {field_name} date: {date_str}")

                if not await click_date_field(field_name):
                    print(f"[Smoothcomp] Could not click {field_name} field")
                    return False

                await page.wait_for_timeout(500)

                keyboard = page.keyboard
                # Select all (Ctrl+A) and delete.
                await keyboard.press("Control+a")
                await page.wait_for_timeout(200)
                await keyboard.press("Backspace")
                await page.wait_for_timeout(200)

                # Type the date in.
                await keyboard.type(date_str)
                await page.wait_for_timeout(500)

                # Confirm with Tab.
                await keyboard.press("Tab")
                await page.wait_for_timeout(500)

                print(f"[Smoothcomp] Successfully entered {field_name} date: {date_str}")
                return True

            # Actually apply start/end dates if provided.
>>>>>>> 07d2f1d (Updated the date filter to click)
            if date_from:
                start_date_readable = format_date_for_agent(date_from)
                print(f"[Smoothcomp] Setting start date: {start_date_readable}")

<<<<<<< HEAD
                # Create agent task for start date selection
                start_task = f"""
                On this events page, I need to set the Start date filter to {start_date_readable}.

                Steps:
                1. Find and click on the "Start date" input field or date picker
                2. If a calendar popup appears, navigate to {month_names[int(date_from.split('-')[1])-1]} {date_from.split('-')[0]}
                3. Click on day {int(date_from.split('-')[2])} in the calendar
                4. Make sure the date is selected and the calendar closes

                Do not click on any event links. Focus only on the date filter.
                """

                try:
                    agent = browser_manager.get_agent(raw_session, start_task, max_steps=15)
                    result = agent.run(start_task)
                    print(f"[Smoothcomp] Start date agent result: {result}")
                except Exception as e:
                    print(f"[Smoothcomp] Start date agent failed: {e}")
                    # Try fallback
                    await self._try_date_fallback(page, date_from, 'start')

                await page.wait_for_timeout(2000)

            # Apply end date using agent
=======
>>>>>>> 07d2f1d (Updated the date filter to click)
            if date_to:
                end_date_readable = format_date_for_agent(date_to)
                print(f"[Smoothcomp] Setting end date: {end_date_readable}")

                # Create agent task for end date selection
                end_task = f"""
                On this events page, I need to set the End date filter to {end_date_readable}.

                Steps:
                1. Find and click on the "End date" input field or date picker
                2. If a calendar popup appears, navigate to {month_names[int(date_to.split('-')[1])-1]} {date_to.split('-')[0]}
                3. Click on day {int(date_to.split('-')[2])} in the calendar
                4. Make sure the date is selected and the calendar closes

                Do not click on any event links. Focus only on the date filter.
                """

                try:
                    agent = browser_manager.get_agent(raw_session, end_task, max_steps=15)
                    result = agent.run(end_task)
                    print(f"[Smoothcomp] End date agent result: {result}")
                except Exception as e:
                    print(f"[Smoothcomp] End date agent failed: {e}")
                    # Try fallback
                    await self._try_date_fallback(page, date_to, 'end')

                await page.wait_for_timeout(2000)

            print(f"[Smoothcomp] Date filter applied successfully")
            return True

        except Exception as e:
            print(f"[Smoothcomp] Date filter error: {e}")
            import traceback
            traceback.print_exc()
            return False

<<<<<<< HEAD
    async def _try_date_fallback(self, page: NotteSession, date_value: str, field_type: str) -> bool:
        """Fallback method to set date using step() with natural language."""
        try:
            print(f"[Smoothcomp] Trying date fallback for {field_type}: {date_value}")

            raw_session = page.raw_session
            field_label = "Start date" if field_type == 'start' else "End date"

            # Parse the date
            parts = date_value.split('-')
            year, month, day = int(parts[0]), int(parts[1]), int(parts[2])
            month_names = ['January', 'February', 'March', 'April', 'May', 'June',
                          'July', 'August', 'September', 'October', 'November', 'December']
            date_readable = f"{month_names[month-1]} {day}, {year}"

            # Try using step() for natural language interaction
            try:
                if hasattr(raw_session, 'step'):
                    raw_session.step(f"Click on the {field_label} filter field")
                    await page.wait_for_timeout(1000)
                    raw_session.step(f"Navigate the calendar to {month_names[month-1]} {year}")
                    await page.wait_for_timeout(500)
                    raw_session.step(f"Click on day {day}")
                    await page.wait_for_timeout(500)
                    print(f"[Smoothcomp] Fallback step() completed for {field_type}")
                    return True
            except Exception as e:
                print(f"[Smoothcomp] step() fallback failed: {e}")

            # Last resort: try keyboard entry
            try:
                await page.action(f"click on the {field_label} input field")
                await page.wait_for_timeout(500)
                keyboard = page.keyboard
                await keyboard.press("Control+a")
                await page.wait_for_timeout(100)
                await keyboard.type(date_value)
                await page.wait_for_timeout(300)
                await keyboard.press("Escape")
                await page.wait_for_timeout(300)
                print(f"[Smoothcomp] Keyboard fallback completed for {field_type}")
                return True
            except Exception as e:
                print(f"[Smoothcomp] Keyboard fallback failed: {e}")

            return False

        except Exception as e:
            print(f"[Smoothcomp] Date fallback failed: {e}")
            return False
=======
    # ---- SCRAPE EVENTS LISTING PAGE ----
>>>>>>> 07d2f1d (Updated the date filter to click)

    async def _scrape_events_page(
        self,
        page: NotteSession,
        location: Optional[str] = None,
        date_from: Optional[str] = None,
        date_to: Optional[str] = None
    ) -> List[Tournament]:
        """
        Scrape tournaments from Smoothcomp's upcoming events page.

        High-level flow:
          1. Go to the upcoming events page.
          2. Handle cookie popup.
          3. Optionally apply a country filter in the UI.
          4. Scroll the page so more events load.
          5. Use Notte's scraping to extract event IDs from visible cards.
          6. Build unique URLs to individual events.
          7. For each event (up to a limit), open the detail page and parse it.
          8. Return a list of Tournament objects.
        """
        tournaments = []

        # Normalize the location filter into a list of lowercase country names.
        target_countries = []
        if location:
            target_countries = [c.strip().lower() for c in location.split(',') if c.strip()]

        try:
            # Navigate to the main events listing page.
            url = self.events_url

            print(f"[Smoothcomp] Navigating to {url}")
            await page.goto(url, wait_until='domcontentloaded')
            await page.wait_for_timeout(3000)
            print(f"[Smoothcomp] Page loaded, current URL: {page.url}")

            # Handle cookie popup (if any) to prevent it blocking controls.
            await self._handle_cookie_popup(page)

<<<<<<< HEAD
            # Apply date filter first (if provided)
            if date_from or date_to:
                print(f"[Smoothcomp] Applying date filter: {date_from} to {date_to}")
                await self._apply_date_filter(page, date_from, date_to)
                await page.wait_for_timeout(2000)  # Wait for results to update

            # Apply country filter using natural language actions
=======
            if date_from or date_to:
            print(f"[Smoothcomp] Applying date filter in UI: {date_from} -> {date_to}")
            await self._apply_date_filter(page, date_from, date_to)
    
            # Apply country filter if the user requested specific locations.
>>>>>>> 07d2f1d (Updated the date filter to click)
            if location:
                print(f"[Smoothcomp] Applying country filter for: {target_countries}")
                await self._apply_country_filter(page, location)

            # Give the page some time to reload with the filters.
            print("[Smoothcomp] Waiting for filtered results to load...")
            await page.wait_for_timeout(3000)

            # Smoothcomp may load more events when you scroll down.
            print("[Smoothcomp] Scrolling to load more filtered events...")
            for i in range(2):
                print(f"[Smoothcomp] Scroll {i+1}/2...")
                await page.evaluate('window.scrollTo(0, document.body.scrollHeight)')
                await page.wait_for_timeout(2000)

            # Now ask Notte to read visible event cards and scrape links.
            print("[Smoothcomp] Asking Notte to read visible event cards...")
            unique_urls = []
            seen = set()  # keep track of event IDs we've already seen.

            try:
                # Use Notte's scrape API to get the main content and links.
                result = page.raw_session.scrape(scrape_links=True, only_main_content=True)

                # Extract text from the scrape result.
                if hasattr(result, 'markdown') and result.markdown:
                    content = result.markdown
                elif hasattr(result, 'text') and result.text:
                    content = result.text
                else:
                    content = str(result)

                print(f"[Smoothcomp] Filtered content length: {len(content)} chars")
                print(f"[Smoothcomp] Content preview: {content[:500]}...")

                # Regex pattern to extract event IDs from links like:
                # "smoothcomp.com/en/event/12345"
                url_pattern = r'smoothcomp\.com/en/event/(\d+)'
                event_ids = re.findall(url_pattern, content)

                for event_id in event_ids:
                    if event_id not in seen:
                        seen.add(event_id)
                        url = f"{self.base_url}/en/event/{event_id}"
                        unique_urls.append(url)
                        print(f"[Smoothcomp] Found filtered event: {url}")

                print(f"[Smoothcomp] Found {len(unique_urls)} events in filtered view")

            except Exception as e:
                # If Notte's scrape fails for some reason, fall back to raw HTML.
                print(f"[Smoothcomp] Scrape failed: {e}, trying fallback...")
                content = await page.content()
                url_pattern = r'smoothcomp\.com/en/event/(\d+)'
                event_ids = re.findall(url_pattern, content)
                for event_id in event_ids[:30]:  # Limit to 30 in fallback mode.
                    if event_id not in seen:
                        seen.add(event_id)
                        unique_urls.append(f"{self.base_url}/en/event/{event_id}")

            # If many events are found, filters might not have been applied correctly.
            if len(unique_urls) > 50:
                print(f"[Smoothcomp] WARNING: Found {len(unique_urls)} events - filters may not have worked")
                print(f"[Smoothcomp] Limiting to first 30 events")
                unique_urls = unique_urls[:30]

            # The old HTML parsing logic is skipped by setting event_links to [].
            event_links = []

            for link in event_links:
                # (Currently unused code; kept for potential future improvements.)
                href = link.get('href', '')
                if href and '/en/event/' in href:
                    event_id = href.split('/en/event/')[-1].split('/')[0]
                    if event_id and event_id not in seen:
                        if target_countries:
                            parent = link.find_parent(['div', 'article', 'li', 'section'])
                            if parent:
                                card_text = parent.get_text(separator=' ', strip=True).lower()
                                country_found = any(country in card_text for country in target_countries)
                                if not country_found:
                                    continue
                                matched = [c for c in target_countries if c in card_text]
                                print(f"[Smoothcomp] Found event card mentioning: {matched}")

                        seen.add(event_id)
                        if href.startswith('/'):
                            full_url = self.base_url + href
                        else:
                            full_url = href
                        unique_urls.append(full_url)

            print(f"[Smoothcomp] Found {len(unique_urls)} events matching '{target_countries or 'all locations'}'")

            if target_countries and len(unique_urls) == 0:
                print(f"[Smoothcomp] WARNING: No events found for '{target_countries}' on listing page")
                print(f"[Smoothcomp] The country filter may not have worked. Check if countries are spelled correctly.")

            # To avoid overwhelming the site or our system, cap how many event pages we visit.
            max_events = 20
            urls_to_scrape = unique_urls[:max_events]
            print(f"[Smoothcomp] Scraping details for {len(urls_to_scrape)} events...")

            # Visit each event detail page and parse full info.
            for i, url in enumerate(urls_to_scrape):
                try:
                    print(f"[Smoothcomp] [{i+1}/{len(urls_to_scrape)}] Scraping {url}")
                    tournament = await self._scrape_event_detail(page, url, target_location=location)
                    if tournament:
                        tournaments.append(tournament)
                        print(f"[Smoothcomp] Added: {tournament.name[:40]}...")
                except Exception as e:
                    print(f"[Smoothcomp] Error scraping event detail: {e}")
                    continue

            print(f"[Smoothcomp] Successfully scraped {len(tournaments)} tournaments")

        except Exception as e:
            print(f"[Smoothcomp] Error scraping events page: {e}")
            import traceback
            traceback.print_exc()

        # Return whatever tournaments we managed to scrape.
        return tournaments

    # ---- SCRAPE A SINGLE EVENT DETAIL PAGE ----

    async def _scrape_event_detail(self, page: NotteSession, url: str, target_location: Optional[str] = None) -> Optional[Tournament]:
        """
        Scrape full details of a single Smoothcomp event.

        Steps:
          1. Navigate to the event URL.
          2. Parse HTML with BeautifulSoup.
          3. Extract:
             - Name
             - Location
             - Organizer
             - Registration fees
             - Event date
          4. Normalize location into city/state/country.
          5. Build and return a Tournament object.
        """
        try:
            # Go to the event page and wait a bit.
            await page.goto(url, wait_until='domcontentloaded')
            await page.wait_for_timeout(2000)

            # Get HTML content and turn it into a BeautifulSoup object.
            content = await page.content()
            soup = BeautifulSoup(content, 'lxml')
            page_text = soup.get_text(separator=' ', strip=True)

            # ----- NAME EXTRACTION -----

            name = None
            h1 = soup.select_one('h1')
            if h1:
                name = h1.get_text(strip=True)
                # Remove trailing dates from the name if present.
                name = re.sub(
                    r'\d{1,2}\s+(Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[a-z]*.*$',
                    '',
                    name,
                    flags=re.IGNORECASE
                ).strip()

            # If no <h1> was found, try the <title> tag.
            if not name:
                title = soup.select_one('title')
                if title:
                    name = title.get_text(strip=True).split(' - ')[0].split('|')[0].strip()

            if not name:
                # If we still can't find a name, give up on this event.
                return None

            # ----- LOCATION EXTRACTION -----

            location = "TBD"

            # Try to find location in dedicated HTML elements first.
            location_selectors = [
                '[class*="location"]',
                '[class*="venue"]',
                '[class*="address"]',
                'address',
            ]
            for sel in location_selectors:
                loc_elem = soup.select_one(sel)
                if loc_elem:
                    loc_text = loc_elem.get_text(separator=', ', strip=True)
                    # Filter obviously irrelevant or too long texts.
                    if loc_text and len(loc_text) < 200 and 'Smoothcomp' not in loc_text and 'Contact' not in loc_text:
                        location = loc_text
                        print(f"[Smoothcomp] Found location from element {sel}: '{location[:50]}...'")
                        break

            # If we didn't get location from HTML elements, try regex on page text.
            if location == "TBD":
                loc_match = re.search(r'Location\s+([A-Z][^,]+(?:,\s*[A-Z][^,]+){0,3})', page_text)
                if loc_match:
                    location = loc_match.group(1).strip()[:100]
                    print(f"[Smoothcomp] Found location from 'Location' header: '{location}'")

            # If still TBD, search for known country names and guess "City, Country".
            if location == "TBD":
                countries = [
                    'Malaysia', 'Singapore', 'Indonesia', 'Thailand', 'Philippines',
                    'Australia', 'Japan', 'USA', 'United States', 'India', 'Hong Kong',
                    'South Korea', 'United Kingdom', 'UK', 'Canada', 'New Zealand', 'Brazil'
                ]
                for country in countries:
                    if country.lower() in page_text.lower():
                        pattern = rf'([A-Z][a-zA-Z\s]+(?:,\s*[A-Z][a-zA-Z\s]+)?),?\s*{country}'
                        match = re.search(pattern, page_text)
                        if match:
                            location = f"{match.group(1).strip()}, {country}"
                            print(f"[Smoothcomp] Found location from country pattern: '{location}'")
                            break
                        else:
                            location = country
                            print(f"[Smoothcomp] Using just country: '{location}'")

            # ----- ORGANIZER EXTRACTION -----

            organizer = None
            # Look for text like "Organizer [Name] 5 year on Smoothcomp".
            org_match = re.search(
                r'(?:Organizer|merchant)[^A-Za-z]*([A-Z][A-Za-z]+(?:\s+[A-Z][a-z]+)+)(?:\s*\d|\s+year|\s+event)',
                page_text
            )
            if org_match:
                organizer = org_match.group(1).strip()

            # Alternative pattern: "[Name] 5 year on Smoothcomp"
            if not organizer:
                org_match = re.search(
                    r'([A-Z][A-Za-z]+(?:\s+[A-Z][a-z]+){1,4})\s+\d+\s+year',
                    page_text
                )
                if org_match:
                    organizer = org_match.group(1).strip()

            # Filter out obvious non-organizer words.
            if organizer and organizer.lower() in ['cancel', 'download', 'accept', 'submit', 'register', 'login', 'sign']:
                organizer = None

            # ----- FEES (REGISTRATION PRICE) EXTRACTION -----

            fees = None
            # Look for currency + number, e.g. "RM185", "USD 85.00", "$100".
            price_matches = re.findall(
                r'(RM|USD|\$|€|£|SGD|THB|IDR|PHP|AUD|JPY)\s*(\d+(?:,\d{3})*(?:\.\d{2})?)',
                page_text
            )
            if price_matches:
                prices = []
                for currency, amount in price_matches:
                    try:
                        num = float(amount.replace(',', ''))
                        prices.append((num, f"{currency}{amount}"))
                    except:
                        pass
                if prices:
                    prices.sort(key=lambda x: x[0])
                    if len(prices) > 1:
                        fees = f"{prices[0][1]} - {prices[-1][1]}"
                    else:
                        fees = prices[0][1]

            # ----- DATE EXTRACTION -----

            date_str = None
            print(f"[Smoothcomp] === DATE EXTRACTION DEBUG ===")

            # 1) Look for "Event dates 10 Jan - 11 Jan 2026"
            date_match = re.search(
                r'Event\s+dates?\s*[:\s]*(\d{1,2}\s+(?:Jan(?:uary)?|Feb(?:ruary)?|Mar(?:ch)?|Apr(?:il)?|May|'
                r'Jun(?:e)?|Jul(?:y)?|Aug(?:ust)?|Sep(?:tember)?|Oct(?:ober)?|Nov(?:ember)?|Dec(?:ember)?)[a-z]*'
                r'(?:\s*[-–&]\s*\d{1,2}\s+(?:Jan(?:uary)?|Feb(?:ruary)?|Mar(?:ch)?|Apr(?:il)?|May|'
                r'Jun(?:e)?|Jul(?:y)?|Aug(?:ust)?|Sep(?:tember)?|Oct(?:ober)?|Nov(?:ember)?|Dec(?:ember)?)[a-z]*)?)'
                r'(?:\s*,?\s*(\d{4}))?',
                page_text,
                re.IGNORECASE
            )
            if date_match:
                date_str = date_match.group(1)
                year = date_match.group(2)
                if year:
                    date_str = f"{date_str} {year}"
                print(f"[Smoothcomp] Found 'Event dates' pattern: '{date_str}'")

            # 2) "10 Jan 2026" type patterns.
            if not date_str:
                date_match = re.search(
                    r'(\d{1,2})\s+(Jan(?:uary)?|Feb(?:ruary)?|Mar(?:ch)?|Apr(?:il)?|May|'
                    r'Jun(?:e)?|Jul(?:y)?|Aug(?:ust)?|Sep(?:tember)?|Oct(?:ober)?|Nov(?:ember)?|Dec(?:ember)?)[a-z]*\s+(\d{4})',
                    page_text,
                    re.IGNORECASE
                )
                if date_match:
                    date_str = date_match.group(0)
                    print(f"[Smoothcomp] Found 'DD Mon YYYY' pattern: '{date_str}'")

            # 3) "January 10, 2026" type patterns.
            if not date_str:
                date_match = re.search(
                    r'(Jan(?:uary)?|Feb(?:ruary)?|Mar(?:ch)?|Apr(?:il)?|May|Jun(?:e)?|Jul(?:y)?|Aug(?:ust)?|'
                    r'Sep(?:tember)?|Oct(?:ober)?|Nov(?:ember)?|Dec(?:ember)?)\s+(\d{1,2})(?:\s*[&,-]\s*\d{1,2})?,?\s*(\d{4})',
                    page_text,
                    re.IGNORECASE
                )
                if date_match:
                    date_str = date_match.group(0)
                    print(f"[Smoothcomp] Found 'Month DD, YYYY' pattern: '{date_str}'")

            # 4) As last resort, "10 Jan" (no year).
            if not date_str:
                date_match = re.search(
                    r'(\d{1,2})\s+(Jan(?:uary)?|Feb(?:ruary)?|Mar(?:ch)?|Apr(?:il)?|May|'
                    r'Jun(?:e)?|Jul(?:y)?|Aug(?:ust)?|Sep(?:tember)?|Oct(?:ober)?|Nov(?:ember)?|Dec(?:ember)?)',
                    page_text,
                    re.IGNORECASE
                )
                if date_match:
                    date_str = date_match.group(0)
                    print(f"[Smoothcomp] Found 'DD Mon' pattern without year: '{date_str}'")

            if not date_str:
                print(f"[Smoothcomp] No date pattern found in page text")
                if 'Event' in page_text:
                    idx = page_text.find('Event')
                    snippet = page_text[max(0, idx):min(len(page_text), idx+200)]
                    print(f"[Smoothcomp] Text near 'Event': '{snippet}'")

            date = self._parse_date(date_str) if date_str else "TBD"
            print(f"[Smoothcomp] Final parsed date: '{date}'")

            # ----- LOCATION COMPONENTS (CITY, STATE, COUNTRY) -----

            city, state, country = self._parse_location(location)

            # If the user requested a specific country (target_location),
            # and that country appears in the page text, we can use it to
            # correct the country field if parsing was weak.
            if target_location:
                target_countries = [c.strip() for c in target_location.split(',') if c.strip()]
                page_text_lower = page_text.lower()
                for target_country in target_countries:
                    if target_country.lower() in page_text_lower:
                        if not country or country == location:
                            country = target_country
                            print(f"[Smoothcomp] Set country to target: '{country}'")
                        if location == "TBD" or "Location" in location:
                            location = target_country
                            print(f"[Smoothcomp] Updated location to: '{location}'")
                        break

            print(f"[Smoothcomp] Detail: name='{name[:30]}...', loc='{location[:30]}...', org='{organizer}', fees='{fees}', date='{date}'")

            # Build and return the Tournament object.
            return Tournament(
                id=self._generate_id(name, date),
                name=name,
                date=date,
                location=location,
                city=city,
                state=state,
                country=country,
                description=None,
                organizer=organizer,
                fees=fees,
                registration_link=url,
                source=self.source,
                sport="BJJ",
            )

        except Exception as e:
            print(f"[Smoothcomp] Error parsing event detail: {e}")
            import traceback
            traceback.print_exc()
            return None

    # ---- DATE PARSING HELPER ----

    def _parse_date(self, date_str: str) -> str:
        """
        Convert a human-readable date string into standard 'YYYY-MM-DD' format.

        Handles:
          - Full dates like '10 January 2026', 'Jan 10, 2026', '2026-01-10'
          - Dates without year like '10 Jan' (then infers year)
          - Numeric formats like '10/01/2026'

        If parsing fails, returns 'TBD'.
        """
        if not date_str:
            return "TBD"

        print(f"[Smoothcomp] _parse_date input: '{date_str}'")

        # Normalize spaces and remove date ranges, keeping only the first date.
        date_str = re.sub(r'\s+', ' ', date_str).strip()
        date_str = re.split(r'\s*[-–&]\s*\d', date_str)[0].strip()
        print(f"[Smoothcomp] _parse_date cleaned: '{date_str}'")

        # Formats that include a year.
        formats_with_year = [
            "%Y-%m-%d",
            "%d %B %Y",      # 10 January 2026
            "%d %b %Y",      # 10 Jan 2026
            "%B %d, %Y",     # January 10, 2026
            "%b %d, %Y",     # Jan 10, 2026
            "%B %d %Y",      # January 10 2026
            "%b %d %Y",      # Jan 10 2026
            "%Y %B %d",      # 2026 January 10
            "%Y %b %d",      # 2026 Jan 10
            "%d/%m/%Y",
            "%m/%d/%Y",
        ]

        for fmt in formats_with_year:
            try:
                parsed = datetime.strptime(date_str, fmt)
                result = parsed.strftime("%Y-%m-%d")
                print(f"[Smoothcomp] Parsed with format '{fmt}': {result}")
                return result
            except ValueError:
                continue

        # Formats without year (we'll infer the year).
        formats_no_year = [
            "%d %B",         # 10 January
            "%d %b",         # 10 Jan
            "%B %d",         # January 10
            "%b %d",         # Jan 10
        ]

        current_year = datetime.now().year
        for fmt in formats_no_year:
            try:
                parsed = datetime.strptime(date_str, fmt)
                parsed = parsed.replace(year=current_year)
                # If the parsed date is more than 30 days in the past, assume it's next year.
                if parsed < datetime.now() - timedelta(days=30):
                    parsed = parsed.replace(year=current_year + 1)
                result = parsed.strftime("%Y-%m-%d")
                print(f"[Smoothcomp] Parsed with format '{fmt}' (no year): {result}")
                return result
            except ValueError:
                continue

        # Numeric date detection via regex (DD/MM/YYYY or similar).
        match = re.search(r'(\d{1,2})[/\-.](\d{1,2})[/\-.](\d{2,4})', date_str)
        if match:
            day, month, year = match.groups()
            if len(year) == 2:
                year = "20" + year
            result = f"{year}-{month.zfill(2)}-{day.zfill(2)}"
            print(f"[Smoothcomp] Parsed with numeric regex: {result}")
            return result

        print(f"[Smoothcomp] Could not parse date: '{date_str}'")
        return "TBD"

    # ---- LOCATION PARSING HELPER ----

    def _parse_location(self, location: str) -> tuple[Optional[str], Optional[str], Optional[str]]:
        """
        Break a location string into (city, state, country).

        Example:
          "Kuala Lumpur, Wilayah Persekutuan, Malaysia"
            -> city="Kuala Lumpur", state="Wilayah Persekutuan", country="Malaysia"

        Logic:
          - Split by commas.
          - First part = city (if exists).
          - Second part = state (if exists).
          - Last part = country if there are 3+ parts, otherwise second part
            might be used as country.
        """
        if not location or location == "TBD":
            return None, None, None

        parts = [p.strip() for p in location.split(',')]

        city = parts[0] if len(parts) > 0 else None
        state = parts[1] if len(parts) > 1 else None
        country = parts[-1] if len(parts) > 2 else (parts[1] if len(parts) > 1 else None)

        return city, state, country

    # ---- MOCK DATA ----

    def _get_mock_data(self) -> List[Tournament]:
        """
        Return mock data for development/demo purposes.

        For SmoothcompAgent, we currently don't define any mock tournaments,
        so this simply returns an empty list.
        """
        return []
