import re
from typing import List, Optional
from datetime import datetime, timedelta
from bs4 import BeautifulSoup

from .base_agent import BaseTournamentAgent
from ..models import Tournament, TournamentSource
from ..browser.manager import NotteSession, NotteContext


class NAGAAgent(BaseTournamentAgent):
    """Agent for scraping tournaments from NAGA using Notte AI (no login required)."""

    @property
    def source(self) -> TournamentSource:
        return TournamentSource.NAGA

    @property
    def base_url(self) -> str:
        return "https://www.nagafighter.com"

    @property
    def events_url(self) -> str:
        return "https://www.nagafighter.com/events"

    @property
    def login_url(self) -> str:
        return "https://www.nagafighter.com/login"

    @property
    def requires_login(self) -> bool:
        """NAGA events are publicly viewable."""
        return False

    @property
    def email_env_var(self) -> str:
        return "NAGA_EMAIL"

    @property
    def password_env_var(self) -> str:
        return "NAGA_PASSWORD"

    async def _check_logged_in(self, page: NotteSession) -> bool:
        """Not required for NAGA - public page."""
        return True

    async def _login(self, page: NotteSession, context: NotteContext) -> bool:
        """Not required for NAGA - public page."""
        return True

    async def _scrape_events_page(
        self,
        page: NotteSession,
        location: Optional[str] = None,
        date_from: Optional[str] = None,
        date_to: Optional[str] = None
    ) -> List[Tournament]:
        """Scrape tournaments from NAGA events page.

        Location can be a single country or comma-separated list (e.g., "Malaysia,Taiwan")
        Note: date_from and date_to are accepted but not used (NAGA doesn't have date filters)
        """
        tournaments = []

        # Parse comma-separated countries for filtering
        target_countries = []
        if location:
            target_countries = [c.strip().lower() for c in location.split(',') if c.strip()]

        try:
            await page.goto(self.events_url, wait_until='domcontentloaded')
            await page.wait_for_timeout(3000)

            for _ in range(3):
                await page.evaluate('window.scrollTo(0, document.body.scrollHeight)')
                await page.wait_for_timeout(1500)

            content = await page.content()
            soup = BeautifulSoup(content, 'lxml')

            event_selectors = [
                '.event-card',
                '.event-item',
                '.tournament-listing',
                '[class*="event"]',
                'article',
                '.card',
            ]

            events = []
            for selector in event_selectors:
                events = soup.select(selector)
                if events:
                    break

            if not events:
                event_links = soup.select('a[href*="/event"]')
                for link in event_links:
                    parent = link.find_parent(['div', 'article', 'li'])
                    if parent and parent not in events:
                        events.append(parent)

            for event in events[:50]:
                try:
                    tournament = self._parse_event_element(event)
                    if tournament:
                        # Filter by target countries if specified
                        if target_countries:
                            tournament_loc = tournament.location.lower() if tournament.location else ""
                            tournament_city = tournament.city.lower() if tournament.city else ""
                            tournament_state = tournament.state.lower() if tournament.state else ""
                            tournament_country = tournament.country.lower() if tournament.country else ""

                            # Check if ANY target country matches
                            matches = any(
                                country in tournament_loc or
                                country in tournament_city or
                                country in tournament_state or
                                country in tournament_country
                                for country in target_countries
                            )
                            if not matches:
                                continue
                        tournaments.append(tournament)
                except Exception as e:
                    print(f"Error parsing NAGA event: {e}")
                    continue

        except Exception as e:
            print(f"Error scraping NAGA events: {e}")

        return tournaments

    def _parse_event_element(self, element) -> Optional[Tournament]:
        """Parse a BeautifulSoup element into a Tournament object."""
        try:
            name_elem = element.select_one('h2, h3, h4, .event-title, .event-name, [class*="title"]')
            name = name_elem.get_text(strip=True) if name_elem else None

            if not name:
                link = element.select_one('a[href*="/event"]')
                if link:
                    name = link.get_text(strip=True)

            if not name:
                return None

            date_elem = element.select_one('[class*="date"], time, .event-date')
            date_str = date_elem.get_text(strip=True) if date_elem else None
            date = self._parse_date(date_str) if date_str else "TBD"

            location_elem = element.select_one('[class*="location"], [class*="venue"], .event-location')
            location = location_elem.get_text(strip=True) if location_elem else "TBD"

            link_elem = element.select_one('a[href*="/event"]')
            if link_elem and link_elem.get('href'):
                href = link_elem['href']
                registration_link = href if href.startswith('http') else self.base_url + href
            else:
                registration_link = self.events_url

            city, state, country = self._parse_location(location)

            return Tournament(
                id=self._generate_id(name, date),
                name=name,
                date=date,
                location=location,
                city=city,
                state=state,
                country=country,
                description=None,
                organizer="NAGA",
                fees=None,
                registration_link=registration_link,
                source=self.source,
                sport="Grappling/BJJ",
            )

        except Exception as e:
            print(f"Error parsing NAGA event element: {e}")
            return None

    def _parse_date(self, date_str: str) -> str:
        """Parse date string into YYYY-MM-DD format."""
        if not date_str:
            return "TBD"

        formats = [
            "%Y-%m-%d",
            "%d/%m/%Y",
            "%m/%d/%Y",
            "%B %d, %Y",
            "%b %d, %Y",
            "%d %B %Y",
        ]

        date_str = re.sub(r'\s+', ' ', date_str).strip()

        for fmt in formats:
            try:
                parsed = datetime.strptime(date_str, fmt)
                return parsed.strftime("%Y-%m-%d")
            except ValueError:
                continue

        match = re.search(r'(\d{1,2})[/\-.](\d{1,2})[/\-.](\d{2,4})', date_str)
        if match:
            day, month, year = match.groups()
            if len(year) == 2:
                year = "20" + year
            return f"{year}-{month.zfill(2)}-{day.zfill(2)}"

        return "TBD"

    def _parse_location(self, location: str) -> tuple[Optional[str], Optional[str], Optional[str]]:
        """Parse location string into city, state, country."""
        if not location or location == "TBD":
            return None, None, None

        parts = [p.strip() for p in location.split(',')]
        city = parts[0] if len(parts) > 0 else None
        state = parts[1] if len(parts) > 1 else None
        country = parts[-1] if len(parts) > 2 else "USA"

        return city, state, country

    def _get_mock_data(self) -> List[Tournament]:
        """Return empty list - no mock data."""
        return []
