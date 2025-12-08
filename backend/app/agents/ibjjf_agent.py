import re
from typing import List, Optional
from datetime import datetime, timedelta
import random
from playwright.async_api import Page, BrowserContext
from bs4 import BeautifulSoup

from .base_agent import BaseTournamentAgent
from ..models import Tournament, TournamentSource


class IBJJFAgent(BaseTournamentAgent):
    """Agent for scraping tournaments from IBJJF using Playwright."""

    @property
    def source(self) -> TournamentSource:
        return TournamentSource.IBJJF

    @property
    def base_url(self) -> str:
        return "https://ibjjf.com"

    @property
    def events_url(self) -> str:
        return "https://ibjjf.com/events"

    @property
    def login_url(self) -> str:
        return "https://ibjjf.com/login"

    @property
    def email_env_var(self) -> str:
        return "IBJJF_EMAIL"

    @property
    def password_env_var(self) -> str:
        return "IBJJF_PASSWORD"

    async def _check_logged_in(self, page: Page) -> bool:
        """Check if already logged in to IBJJF."""
        try:
            await page.goto(self.base_url, wait_until='domcontentloaded')
            await page.wait_for_timeout(2000)

            # Check for logged in indicators
            logged_in_selectors = [
                '.user-menu',
                '.profile-dropdown',
                'a[href*="/profile"]',
                'a[href*="/logout"]',
                'a[href*="/my-account"]',
                '.logged-in',
            ]

            for selector in logged_in_selectors:
                element = await page.query_selector(selector)
                if element:
                    return True

            # Check if login link is present
            login_link = await page.query_selector('a[href*="/login"]')
            if login_link:
                return False

            return False
        except Exception as e:
            print(f"Error checking IBJJF login status: {e}")
            return False

    async def _login(self, page: Page, context: BrowserContext) -> bool:
        """Login to IBJJF."""
        email, password = self.get_credentials()
        if not email or not password:
            return False

        try:
            await page.goto(self.login_url, wait_until='domcontentloaded')
            await page.wait_for_timeout(2000)

            # Fill login form
            email_selectors = [
                'input[name="email"]',
                'input[type="email"]',
                '#email',
                'input[name="username"]',
                '#username',
            ]

            password_selectors = [
                'input[name="password"]',
                'input[type="password"]',
                '#password',
            ]

            # Find and fill email
            for selector in email_selectors:
                try:
                    element = await page.query_selector(selector)
                    if element:
                        await page.fill(selector, email)
                        break
                except Exception:
                    continue

            # Find and fill password
            for selector in password_selectors:
                try:
                    element = await page.query_selector(selector)
                    if element:
                        await page.fill(selector, password)
                        break
                except Exception:
                    continue

            # Submit form
            submit_selectors = [
                'button[type="submit"]',
                'input[type="submit"]',
                'button:has-text("Log in")',
                'button:has-text("Sign in")',
                'button:has-text("Login")',
                '.login-button',
            ]

            for selector in submit_selectors:
                try:
                    element = await page.query_selector(selector)
                    if element:
                        await page.click(selector)
                        break
                except Exception:
                    continue

            await page.wait_for_timeout(3000)
            await page.wait_for_load_state('networkidle', timeout=10000)

            logged_in = await self._check_logged_in(page)
            if logged_in:
                await self._save_session(context)
                return True

            return False

        except Exception as e:
            print(f"IBJJF login error: {e}")
            return False

    async def _scrape_events_page(self, page: Page, location: Optional[str] = None) -> List[Tournament]:
        """Scrape tournaments from IBJJF events page."""
        tournaments = []

        try:
            await page.goto(self.events_url, wait_until='domcontentloaded')
            await page.wait_for_timeout(3000)

            # Scroll to load more events
            for _ in range(3):
                await page.evaluate('window.scrollTo(0, document.body.scrollHeight)')
                await page.wait_for_timeout(1500)

            content = await page.content()
            soup = BeautifulSoup(content, 'lxml')

            # IBJJF typically displays events in cards or list items
            event_selectors = [
                '.event-card',
                '.event-item',
                '.tournament-card',
                '[class*="event"]',
                'article',
            ]

            events = []
            for selector in event_selectors:
                events = soup.select(selector)
                if events:
                    break

            # Look for event links if no containers found
            if not events:
                event_links = soup.select('a[href*="/events/"]')
                for link in event_links:
                    parent = link.find_parent(['div', 'article', 'li', 'section'])
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
                    print(f"Error parsing IBJJF event: {e}")
                    continue

        except Exception as e:
            print(f"Error scraping IBJJF events: {e}")

        return tournaments

    def _parse_event_element(self, element) -> Optional[Tournament]:
        """Parse a BeautifulSoup element into a Tournament object."""
        try:
            # Extract name
            name_elem = element.select_one('h2, h3, h4, .event-title, .event-name, [class*="title"]')
            name = name_elem.get_text(strip=True) if name_elem else None

            if not name:
                link = element.select_one('a[href*="/events/"]')
                if link:
                    name = link.get_text(strip=True)

            if not name:
                return None

            # Extract date
            date_elem = element.select_one('[class*="date"], time, .event-date')
            date_str = date_elem.get_text(strip=True) if date_elem else None
            date = self._parse_date(date_str) if date_str else "TBD"

            # Extract location
            location_elem = element.select_one('[class*="location"], [class*="venue"], .event-location')
            location = location_elem.get_text(strip=True) if location_elem else "TBD"

            # Extract link
            link_elem = element.select_one('a[href*="/events/"]')
            if link_elem and link_elem.get('href'):
                href = link_elem['href']
                registration_link = href if href.startswith('http') else self.base_url + href
            else:
                registration_link = self.events_url

            # Parse location
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
                organizer="IBJJF",
                fees=None,
                registration_link=registration_link,
                source=self.source,
                sport="BJJ",
            )

        except Exception as e:
            print(f"Error parsing IBJJF event element: {e}")
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
            "%d %b %Y",
            "%B %d-%d, %Y",
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
        """Parse location string into components."""
        if not location or location == "TBD":
            return None, None, None

        parts = [p.strip() for p in location.split(',')]
        city = parts[0] if len(parts) > 0 else None
        state = parts[1] if len(parts) > 1 else None
        country = parts[-1] if len(parts) > 2 else (parts[1] if len(parts) > 1 else None)

        return city, state, country

    def _get_mock_data(self) -> List[Tournament]:
        """Return realistic mock data for IBJJF tournaments."""
        base_date = datetime.now()

        mock_tournaments = [
            {
                "name": "IBJJF World Championship",
                "city": "Long Beach",
                "state": "CA",
                "country": "USA",
                "fees": "$150 - $250",
                "description": "The most prestigious BJJ tournament in the world. All belt levels.",
                "days_offset": 90
            },
            {
                "name": "IBJJF Pan Championship",
                "city": "Kissimmee",
                "state": "FL",
                "country": "USA",
                "fees": "$140 - $220",
                "description": "Pan American Championship. Major IBJJF event with worldwide competitors.",
                "days_offset": 45
            },
            {
                "name": "IBJJF European Championship",
                "city": "Lisbon",
                "state": "",
                "country": "Portugal",
                "fees": "€120 - €180",
                "description": "European Championship with competitors from across Europe and beyond.",
                "days_offset": 60
            },
            {
                "name": "IBJJF Dallas Open",
                "city": "Dallas",
                "state": "TX",
                "country": "USA",
                "fees": "$100 - $140",
                "description": "Open tournament with Gi and No-Gi divisions. All belt levels welcome.",
                "days_offset": 21
            },
            {
                "name": "IBJJF Atlanta Spring Open",
                "city": "Atlanta",
                "state": "GA",
                "country": "USA",
                "fees": "$100 - $140",
                "description": "Spring open tournament. Points towards IBJJF ranking.",
                "days_offset": 30
            },
            {
                "name": "IBJJF Houston Open",
                "city": "Houston",
                "state": "TX",
                "country": "USA",
                "fees": "$100 - $140",
                "description": "Open tournament in Houston. IBJJF rules and regulations.",
                "days_offset": 50
            },
            {
                "name": "IBJJF San Diego Open",
                "city": "San Diego",
                "state": "CA",
                "country": "USA",
                "fees": "$100 - $140",
                "description": "Southern California open. Great preparation for Worlds.",
                "days_offset": 75
            },
            {
                "name": "IBJJF No-Gi World Championship",
                "city": "Anaheim",
                "state": "CA",
                "country": "USA",
                "fees": "$150 - $250",
                "description": "World Championship in No-Gi format. Submission wrestling focus.",
                "days_offset": 120
            },
        ]

        tournaments = []
        for t in mock_tournaments:
            date = base_date + timedelta(days=t["days_offset"])
            end_date = date + timedelta(days=random.choice([1, 2, 3]))
            tournament = Tournament(
                id=self._generate_id(t["name"], date.strftime("%Y-%m-%d")),
                name=t["name"],
                date=date.strftime("%Y-%m-%d"),
                end_date=end_date.strftime("%Y-%m-%d"),
                location=f"{t['city']}, {t['state']}, {t['country']}".replace(", ,", ",").strip(", "),
                city=t["city"],
                state=t["state"] if t["state"] else None,
                country=t["country"],
                description=t["description"],
                organizer="IBJJF",
                fees=t["fees"],
                registration_link=f"https://ibjjf.com/events/{self._generate_id(t['name'], '')}",
                source=self.source,
                sport="BJJ",
                registration_deadline=(date - timedelta(days=14)).strftime("%Y-%m-%d"),
            )
            tournaments.append(tournament)

        return tournaments
