import os
import hashlib
from abc import ABC, abstractmethod
from typing import List, Optional, TYPE_CHECKING

from ..models import Tournament, TournamentSource
from ..browser.manager import get_browser_manager, BrowserManager, NotteSession, NotteContext

class BaseTournamentAgent(ABC):
    """
    Base class (or "template") for all tournament scraping agents.

    This class:
      - Knows how to set up and manage the browser session (with Notte).
      - Handles login logic in a generic way.
      - Calls child class methods to do site-specific work
        (like going to Smoothcomp or IBJJF and scraping their pages).

    Child classes MUST fill in:
      - What source they are (Smoothcomp, IBJJF, etc.).
      - What URLs to use (base URL, events page, login page).
      - How to check if they are logged in for that site.
      - How to perform login for that site.
      - How to scrape the events page for that site.
      - Optionally: how to provide mock/demo data.
    """

    def __init__(self):
        """
        Constructor: runs when you create a new agent object.

        Here we:
          - Decide where to store the browser "session state" on disk,
            so we can reuse logins across future runs.
          - Make sure the storage folder exists.
        """
        # Build path like:
        # <this_file_folder>/../../storage/<SOURCE_VALUE>_state.json
        # For example: storage/SMOOTHCOMP_state.json
        self.storage_state_path = os.path.join(
            os.path.dirname(__file__),  # folder where *this* file lives
            '..', '..', 'storage',      # go up two levels, into 'storage'
            f'{self.source.value}_state.json'  # file name based on source
        )

        # Ensure the folder for storing the state actually exists.
        # exist_ok=True means "don't crash if it's already there."
        os.makedirs(os.path.dirname(self.storage_state_path), exist_ok=True)

    # ---- REQUIRED PROPERTIES (child classes MUST override) ----

    @property
    @abstractmethod
    def source(self) -> TournamentSource:
        """
        The "source" enum value for this agent.

        Example:
          - TournamentSource.SMOOTHCOMP
          - TournamentSource.IBJJF

        This is used for:
          - Logging.
          - Generating unique tournament IDs.
          - Knowing which site this agent represents.
        """
        pass

    @property
    @abstractmethod
    def base_url(self) -> str:
        """
        The base URL of the tournament site.

        Example:
          - "https://smoothcomp.com"
        """
        pass

    @property
    @abstractmethod
    def events_url(self) -> str:
        """
        The URL to the page that lists tournaments/events.

        Example:
          - "https://smoothcomp.com/en/events/upcoming"
        """
        pass

    @property
    @abstractmethod
    def login_url(self) -> str:
        """
        The URL to the login page.

        If the site needs you to log in to see events,
        the child class will return something like:
          - "https://smoothcomp.com/en/login"

        If the site is public only, this still needs to be defined,
        but may not be used.
        """
        pass

    @property
    def requires_login(self) -> bool:
        """
        Whether this source requires authentication (login) BEFORE scraping.

        The default here is True (we assume most sites need login).
        Child classes can override this to False if the events page is public.
        """
        return True

    @property
    @abstractmethod
    def email_env_var(self) -> str:
        """
        Name of the environment variable that holds the login email.

        Example:
          - "SMOOTHCOMP_EMAIL"
        """
        pass

    @property
    @abstractmethod
    def password_env_var(self) -> str:
        """
        Name of the environment variable that holds the login password.

        Example:
          - "SMOOTHCOMP_PASSWORD"
        """
        pass

    # ---- CREDENTIAL HELPERS ----

    def get_credentials(self) -> tuple[Optional[str], Optional[str]]:
        """
        Read login credentials from environment variables.

        Returns:
          (email, password) where either can be None if not set.

        Using environment variables helps avoid hard-coding passwords in code.
        """
        email = os.getenv(self.email_env_var)
        password = os.getenv(self.password_env_var)
        return email, password

    def has_credentials(self) -> bool:
        """
        Simple helper to check if BOTH email and password are configured.

        Returns:
          True if both email and password are non-empty, False otherwise.
        """
        email, password = self.get_credentials()
        return bool(email and password)

    # ---- MAIN ENTRYPOINT: SCRAPE TOURNAMENTS ----

    async def scrape_tournaments(
        self,
        location: Optional[str] = None,
        date_from: Optional[str] = None,
        date_to: Optional[str] = None
    ) -> List[Tournament]:
        """
        High-level function to get tournaments from this source using Notte.

        Steps:
          1. Log some info about the scrape.
          2. If login is required, make sure we have credentials.
          3. Get a browser manager.
          4. Restore previous session state if we have it (reuse login).
          5. If login is required:
               - Check if already logged in.
               - If not, perform login.
          6. Call the site-specific _scrape_events_page() to get tournaments.
          7. Return the list of Tournament objects.

        Args:
            location: Optional country/location filter (e.g. "Malaysia,Taiwan")
            date_from: Start date filter (YYYY-MM-DD) as a string.
            date_to: End date filter (YYYY-MM-DD) as a string.

        Returns:
            A list of Tournament objects (could be empty if nothing found).
        """
        print(f"[{self.source.value}] Starting scrape, requires_login={self.requires_login}")
        if date_from or date_to:
            print(f"[{self.source.value}] Date filter: {date_from} to {date_to}")

        # If this site requires login but we don't have credentials,
        # we can't proceed with scraping. So we just log and return empty.
        if self.requires_login and not self.has_credentials():
            print(f"[{self.source.value}] No credentials configured, skipping")
            return []

        try:
            # 1. Get the browser manager that knows how to spawn a browser/context.
            print(f"[{self.source.value}] Getting browser manager...")
            browser_manager = await get_browser_manager()

            # 2. Try to reuse existing session state (cookies, login, etc.).
            #    If the storage_state file exists, use it. Otherwise, None.
            storage_state = self.storage_state_path if os.path.exists(self.storage_state_path) else None
            print(f"[{self.source.value}] Storage state: {storage_state}")

            # 3. Open a new browser context using the (optional) storage state.
            #    This 'async with' ensures that resources are cleaned up automatically.
            async with browser_manager.new_context(storage_state=storage_state) as (context, session):
                # Wrap the raw Notte session into a more convenient NotteSession class.
                page = NotteSession(session)

                # ---- Handle login if needed ----
                if self.requires_login:
                    print(f"[{self.source.value}] Checking login status...")
                    logged_in = await self._check_logged_in(page)
                    if logged_in:
                        print(f"[{self.source.value}] ✓ ALREADY LOGGED IN - Session restored successfully")
                    else:
                        print(f"[{self.source.value}] Not logged in, attempting login...")
                        email, _ = self.get_credentials()
                        print(f"[{self.source.value}] Using credentials for: {email}")
                        success = await self._login(page, context)
                        if success:
                            print(f"[{self.source.value}] ✓ LOGIN SUCCESSFUL - Authenticated with {email}")
                        else:
                            print(f"[{self.source.value}] ✗ LOGIN FAILED - Could not authenticate with {email}")
                            return []
                else:
                    # For public sites (like Smoothcomp events list), we skip login entirely.
                    print(f"[{self.source.value}] No login required for this source")

                # ---- Now actually scrape the events page ----
                print(f"[{self.source.value}] Scraping events page...")
                tournaments = await self._scrape_events_page(page, location, date_from, date_to)

                if tournaments:
                    print(f"[{self.source.value}] Found {len(tournaments)} tournaments")
                else:
                    print(f"[{self.source.value}] No tournaments found")
                return tournaments

        except Exception as e:
            # If anything unexpected goes wrong (network error, site change, etc.),
            # we log the error and return an empty list instead of crashing the program.
            print(f"[{self.source.value}] Error: {e}")
            import traceback
            traceback.print_exc()
            return []

    # ---- ABSTRACT METHODS: MUST BE IMPLEMENTED BY CHILD CLASSES ----

    @abstractmethod
    async def _check_logged_in(self, page: NotteSession) -> bool:
        """
        Child classes must provide logic to detect whether we are
        already logged in on the site.

        Typically:
          - Navigate to base_url.
          - Check for presence of user profile / logout button.
          - Return True if logged in, False otherwise.
        """
        pass

    @abstractmethod
    async def _login(self, page: NotteSession, context: NotteContext) -> bool:
        """
        Perform login to the tournament site.

        Child class should:
          1. Navigate to login page.
          2. Fill in email & password fields.
          3. Click the submit/login button.
          4. Wait for page reload.
          5. Verify login succeeded (maybe reusing _check_logged_in).
          6. If successful, call self._save_session(context) to save cookies.

        Args:
            page: The browser page/session wrapper.
            context: The browser context object (used to save storage state).

        Returns:
            True if login was successful, otherwise False.
        """
        pass

    @abstractmethod
    async def _scrape_events_page(
        self,
        page: NotteSession,
        location: Optional[str] = None,
        date_from: Optional[str] = None,
        date_to: Optional[str] = None
    ) -> List[Tournament]:
        """
        Scrape tournaments from the events listing page.

        Child class must:
          - Go to the events_url.
          - Optionally apply filters like location or date.
          - Scroll/load enough events.
          - Extract links to individual tournaments.
          - Visit each event detail page.
          - Build Tournament objects.

        Args:
            page: Notte session page wrapper (browser tab).
            location: Optional location filter (e.g. "Malaysia,Taiwan").
            date_from: Start date filter (YYYY-MM-DD).
            date_to: End date filter (YYYY-MM-DD).

        Returns:
            List of Tournament objects.
        """
        pass

    @abstractmethod
    def _get_mock_data(self) -> List[Tournament]:
        """
        Return mock/demo data.

        This can be useful for:
          - Development when you don't want to spam the real site.
          - Demos where internet access is not available.

        Child classes can:
          - Return a list of hard-coded Tournament objects.
          - Or return [] if mock data is not used (like SmoothcompAgent does).
        """
        pass

    # ---- UTILITY METHODS SHARED BY ALL AGENTS ----

    def _generate_id(self, name: str, date: str) -> str:
        """
        Generate a short, unique ID for a tournament.

        We combine:
          - source name (e.g. "SMOOTHCOMP")
          - tournament name (e.g. "Grappling Industries KL")
          - date (e.g. "2026-03-10")

        Then:
          - Create an MD5 hash of that combined string.
          - Take the first 12 characters of the hash.

        This gives us a stable ID so we can track tournaments consistently.
        """
        return hashlib.md5(f"{self.source.value}:{name}:{date}".encode()).hexdigest()[:12]

    async def _save_session(self, context: NotteContext):
        """
        Save browser session state (cookies, local storage, etc.) to a file.

        Why we do this:
          - So that next time we run the scraper, we can reuse the session.
          - That often means we stay logged in and skip the login process.

        The file path used is self.storage_state_path (set in __init__).
        """
        try:
            await context.storage_state(path=self.storage_state_path)
            print(f"Session saved for {self.source.value}")
        except Exception as e:
            print(f"Failed to save session for {self.source.value}: {e}")
