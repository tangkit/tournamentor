import re
from typing import List, Optional
from datetime import datetime, timedelta
import random
from playwright.async_api import Page, BrowserContext
from bs4 import BeautifulSoup

from .base_agent import BaseTournamentAgent
from ..models import Tournament, TournamentSource


class GrapplingIndustriesAgent(BaseTournamentAgent):
    """Agent for scraping tournaments from Grappling Industries using Playwright (no login required)."""

    @property
    def source(self) -> TournamentSource:
        return TournamentSource.GRAPPLING_INDUSTRIES

    @property
    def base_url(self) -> str:
        return "https://grapplingindustries.com"

    @property
    def events_url(self) -> str:
        return "https://grapplingindustries.com/events/"

    @property
    def login_url(self) -> str:
        return "https://grapplingindustries.com/login"

    @property
    def requires_login(self) -> bool:
        """Grappling Industries events are publicly viewable."""
        return False

    @property
    def email_env_var(self) -> str:
        return "GI_EMAIL"

    @property
    def password_env_var(self) -> str:
        return "GI_PASSWORD"

    async def _check_logged_in(self, page: Page) -> bool:
        """Not required - public page."""
        return True

    async def _login(self, page: Page, context: BrowserContext) -> bool:
        """Not required - public page."""
        return True

    async def _scrape_events_page(self, page: Page, location: Optional[str] = None) -> List[Tournament]:
        """Scrape tournaments from Grappling Industries events page."""
        tournaments = []

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
                '.tournament-card',
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
                        if location:
                            loc_lower = location.lower()
                            if (loc_lower not in tournament.location.lower() and
                                (not tournament.city or loc_lower not in tournament.city.lower()) and
                                (not tournament.country or loc_lower not in tournament.country.lower())):
                                continue
                        tournaments.append(tournament)
                except Exception as e:
                    print(f"Error parsing Grappling Industries event: {e}")
                    continue

        except Exception as e:
            print(f"Error scraping Grappling Industries events: {e}")

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
                description="Round robin format - guaranteed multiple matches",
                organizer="Grappling Industries",
                fees=None,
                registration_link=registration_link,
                source=self.source,
                sport="BJJ",
            )

        except Exception as e:
            print(f"Error parsing Grappling Industries event element: {e}")
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
        country = parts[-1] if len(parts) > 2 else (parts[1] if len(parts) > 1 else None)

        return city, state, country

    def _get_mock_data(self) -> List[Tournament]:
        """Return realistic mock data for Grappling Industries tournaments."""
        base_date = datetime.now()

        mock_tournaments = [
            {
                "name": "Grappling Industries Toronto",
                "city": "Toronto",
                "state": "ON",
                "country": "Canada",
                "fees": "$90 CAD - $120 CAD",
                "description": "Round robin format. Guaranteed 4+ matches. Gi and No-Gi.",
                "days_offset": 20
            },
            {
                "name": "Grappling Industries London",
                "city": "London",
                "state": "",
                "country": "UK",
                "fees": "£70 - £90",
                "description": "UK's premier round robin BJJ event.",
                "days_offset": 35
            },
            {
                "name": "Grappling Industries Sydney",
                "city": "Sydney",
                "state": "NSW",
                "country": "Australia",
                "fees": "$100 AUD - $130 AUD",
                "description": "Australian round robin championship. Great match experience.",
                "days_offset": 50
            },
            {
                "name": "Grappling Industries Melbourne",
                "city": "Melbourne",
                "state": "VIC",
                "country": "Australia",
                "fees": "$100 AUD - $130 AUD",
                "description": "Melbourne round robin. Growing Victorian BJJ community.",
                "days_offset": 65
            },
            {
                "name": "Grappling Industries Vancouver",
                "city": "Vancouver",
                "state": "BC",
                "country": "Canada",
                "fees": "$90 CAD - $120 CAD",
                "description": "West coast Canadian championship. Beautiful venue.",
                "days_offset": 42
            },
            {
                "name": "Grappling Industries Auckland",
                "city": "Auckland",
                "state": "",
                "country": "New Zealand",
                "fees": "$110 NZD - $140 NZD",
                "description": "New Zealand round robin event. International competitors welcome.",
                "days_offset": 85
            },
            {
                "name": "Grappling Industries Dublin",
                "city": "Dublin",
                "state": "",
                "country": "Ireland",
                "fees": "€75 - €95",
                "description": "Irish championship. Round robin guarantees multiple matches.",
                "days_offset": 55
            },
        ]

        tournaments = []
        for t in mock_tournaments:
            date = base_date + timedelta(days=t["days_offset"])
            location = f"{t['city']}, {t['state']}, {t['country']}" if t["state"] else f"{t['city']}, {t['country']}"
            tournament = Tournament(
                id=self._generate_id(t["name"], date.strftime("%Y-%m-%d")),
                name=t["name"],
                date=date.strftime("%Y-%m-%d"),
                location=location.replace(", ,", ","),
                city=t["city"],
                state=t["state"] if t["state"] else None,
                country=t["country"],
                description=t["description"],
                organizer="Grappling Industries",
                fees=t["fees"],
                registration_link=f"https://grapplingindustries.com/events/{self._generate_id(t['name'], '')}",
                source=self.source,
                sport="BJJ",
                registration_deadline=(date - timedelta(days=7)).strftime("%Y-%m-%d"),
            )
            tournaments.append(tournament)

        return tournaments
