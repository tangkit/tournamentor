import os
import hashlib
from abc import ABC, abstractmethod
from typing import List, Optional, TYPE_CHECKING

from ..models import Tournament, TournamentSource
from ..browser.manager import get_browser_manager, BrowserManager, NotteSession, NotteContext


class BaseTournamentAgent(ABC):
    """Base class for tournament scraping agents using Notte AI."""

    def __init__(self):
        self.storage_state_path = os.path.join(
            os.path.dirname(__file__),
            '..', '..', 'storage',
            f'{self.source.value}_state.json'
        )
        # Ensure storage directory exists
        os.makedirs(os.path.dirname(self.storage_state_path), exist_ok=True)

    @property
    @abstractmethod
    def source(self) -> TournamentSource:
        """The source this agent scrapes from."""
        pass

    @property
    @abstractmethod
    def base_url(self) -> str:
        """The base URL of the tournament site."""
        pass

    @property
    @abstractmethod
    def events_url(self) -> str:
        """The URL to the events/tournaments listing page."""
        pass

    @property
    @abstractmethod
    def login_url(self) -> str:
        """The URL to the login page."""
        pass

    @property
    def requires_login(self) -> bool:
        """Whether this source requires authentication."""
        return True

    @property
    @abstractmethod
    def email_env_var(self) -> str:
        """Environment variable name for email credential."""
        pass

    @property
    @abstractmethod
    def password_env_var(self) -> str:
        """Environment variable name for password credential."""
        pass

    def get_credentials(self) -> tuple[Optional[str], Optional[str]]:
        """Get login credentials from environment variables."""
        email = os.getenv(self.email_env_var)
        password = os.getenv(self.password_env_var)
        return email, password

    def has_credentials(self) -> bool:
        """Check if credentials are configured."""
        email, password = self.get_credentials()
        return bool(email and password)

    async def scrape_tournaments(self, location: Optional[str] = None) -> List[Tournament]:
        """
        Use Notte AI to browse and extract tournament data.

        Args:
            location: Optional location filter

        Returns:
            List of Tournament objects
        """
        print(f"[{self.source.value}] Starting scrape, requires_login={self.requires_login}")

        if self.requires_login and not self.has_credentials():
            print(f"[{self.source.value}] No credentials configured, skipping")
            return []

        try:
            print(f"[{self.source.value}] Getting browser manager...")
            browser_manager = await get_browser_manager()

            # Try to use existing session state
            storage_state = self.storage_state_path if os.path.exists(self.storage_state_path) else None
            print(f"[{self.source.value}] Storage state: {storage_state}")

            async with browser_manager.new_context(storage_state=storage_state) as (context, session):
                # Create page wrapper
                page = NotteSession(session)

                # Check if we need to login
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
                    print(f"[{self.source.value}] No login required for this source")

                # Navigate to events page and scrape
                print(f"[{self.source.value}] Scraping events page...")
                tournaments = await self._scrape_events_page(page, location)

                if tournaments:
                    print(f"[{self.source.value}] Found {len(tournaments)} tournaments")
                else:
                    print(f"[{self.source.value}] No tournaments found")
                return tournaments

        except Exception as e:
            print(f"[{self.source.value}] Error: {e}")
            import traceback
            traceback.print_exc()
            return []

    @abstractmethod
    async def _check_logged_in(self, page: NotteSession) -> bool:
        """Check if already logged in to the site."""
        pass

    @abstractmethod
    async def _login(self, page: NotteSession, context: NotteContext) -> bool:
        """
        Perform login to the tournament site.

        Args:
            page: Notte session page wrapper
            context: Notte context for saving state

        Returns:
            True if login successful
        """
        pass

    @abstractmethod
    async def _scrape_events_page(self, page: NotteSession, location: Optional[str] = None) -> List[Tournament]:
        """
        Scrape tournaments from the events page.

        Args:
            page: Notte session page wrapper (already logged in)
            location: Optional location filter

        Returns:
            List of Tournament objects
        """
        pass

    @abstractmethod
    def _get_mock_data(self) -> List[Tournament]:
        """Return mock data for development/demo purposes."""
        pass

    def _generate_id(self, name: str, date: str) -> str:
        """Generate a unique ID for a tournament."""
        return hashlib.md5(f"{self.source.value}:{name}:{date}".encode()).hexdigest()[:12]

    async def _save_session(self, context: NotteContext):
        """Save browser session state for future use."""
        try:
            await context.storage_state(path=self.storage_state_path)
            print(f"Session saved for {self.source.value}")
        except Exception as e:
            print(f"Failed to save session for {self.source.value}: {e}")
