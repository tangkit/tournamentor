import re
from typing import List, Optional
from datetime import datetime, timedelta
from playwright.async_api import Page, BrowserContext
from bs4 import BeautifulSoup

from .base_agent import BaseTournamentAgent
from ..models import Tournament, TournamentSource


class ASJJFAgent(BaseTournamentAgent):
    """Agent for scraping tournaments from ASJJF using Playwright."""

    @property
    def source(self) -> TournamentSource:
        return TournamentSource.ASJJF

    @property
    def base_url(self) -> str:
        return "https://www.asjjf.org"

    @property
    def events_url(self) -> str:
        return "https://www.asjjf.org/events"

    @property
    def login_url(self) -> str:
        return "https://www.asjjf.org/login"

    @property
    def email_env_var(self) -> str:
        return "ASJJF_EMAIL"

    @property
    def password_env_var(self) -> str:
        return "ASJJF_PASSWORD"

    @property
    def requires_login(self) -> bool:
        """ASJJF events page is public, no login needed."""
        return False

    async def _check_logged_in(self, page: Page) -> bool:
        """Check if already logged in to ASJJF."""
        try:
            await page.goto(self.base_url, wait_until='domcontentloaded')
            await page.wait_for_timeout(2000)

            logged_in_selectors = [
                '.user-menu',
                '.profile-dropdown',
                'a[href*="/profile"]',
                'a[href*="/logout"]',
                'a[href*="/my-account"]',
                '.member-area',
            ]

            for selector in logged_in_selectors:
                element = await page.query_selector(selector)
                if element:
                    return True

            login_link = await page.query_selector('a[href*="/login"]')
            if login_link:
                return False

            return False
        except Exception as e:
            print(f"Error checking ASJJF login status: {e}")
            return False

    async def _login(self, page: Page, context: BrowserContext) -> bool:
        """Login to ASJJF."""
        email, password = self.get_credentials()
        if not email or not password:
            return False

        try:
            await page.goto(self.login_url, wait_until='domcontentloaded')
            await page.wait_for_timeout(2000)

            email_selectors = [
                'input[name="email"]',
                'input[type="email"]',
                '#email',
                'input[name="username"]',
            ]

            password_selectors = [
                'input[name="password"]',
                'input[type="password"]',
                '#password',
            ]

            for selector in email_selectors:
                try:
                    element = await page.query_selector(selector)
                    if element:
                        await page.fill(selector, email)
                        break
                except Exception:
                    continue

            for selector in password_selectors:
                try:
                    element = await page.query_selector(selector)
                    if element:
                        await page.fill(selector, password)
                        break
                except Exception:
                    continue

            submit_selectors = [
                'button[type="submit"]',
                'input[type="submit"]',
                'button:has-text("Log in")',
                'button:has-text("Sign in")',
                'button:has-text("Login")',
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
            print(f"ASJJF login error: {e}")
            return False

    async def _scrape_events_page(self, page: Page, location: Optional[str] = None) -> List[Tournament]:
        """Scrape tournaments from ASJJF events page.

        Location can be a single country or comma-separated list (e.g., "Malaysia,Taiwan")
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
                '.tournament-card',
                '[class*="event"]',
                'article',
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
                            tournament_country = tournament.country.lower() if tournament.country else ""

                            # Check if ANY target country matches
                            matches = any(
                                country in tournament_loc or
                                country in tournament_city or
                                country in tournament_country
                                for country in target_countries
                            )
                            if not matches:
                                continue
                        tournaments.append(tournament)
                except Exception as e:
                    print(f"Error parsing ASJJF event: {e}")
                    continue

        except Exception as e:
            print(f"Error scraping ASJJF events: {e}")

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

            city, country = self._parse_location(location)

            return Tournament(
                id=self._generate_id(name, date),
                name=name,
                date=date,
                location=location,
                city=city,
                country=country,
                description=None,
                organizer="ASJJF",
                fees=None,
                registration_link=registration_link,
                source=self.source,
                sport="BJJ/Judo",
            )

        except Exception as e:
            print(f"Error parsing ASJJF event element: {e}")
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
            "%Y年%m月%d日",
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

    def _parse_location(self, location: str) -> tuple[Optional[str], Optional[str]]:
        """Parse location string into city and country."""
        if not location or location == "TBD":
            return None, None

        parts = [p.strip() for p in location.split(',')]
        city = parts[0] if len(parts) > 0 else None
        country = parts[-1] if len(parts) > 1 else None

        return city, country

    def _get_mock_data(self) -> List[Tournament]:
        """Return empty list - no mock data."""
        return []
