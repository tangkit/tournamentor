import re
from typing import List, Optional
from datetime import datetime, timedelta
from bs4 import BeautifulSoup

from .base_agent import BaseTournamentAgent
from ..models import Tournament, TournamentSource
from ..browser.manager import NotteSession, NotteContext


class ASJJFAgent(BaseTournamentAgent):
    """Agent for scraping tournaments from ASJJF using Notte AI."""

    @property
    def source(self) -> TournamentSource:
        return TournamentSource.ASJJF

    @property
    def base_url(self) -> str:
        return "https://asjjf.org"

    # Season IDs for ASJJF - maps year to season ID
    SEASON_IDS = {
        2024: 229,
        2025: 286,
        2026: 341,
    }

    @property
    def events_url(self) -> str:
        """Default to current year's season."""
        current_year = datetime.now().year
        season_id = self.SEASON_IDS.get(current_year, 286)
        return f"https://asjjf.org/main/eventsBySeason/{season_id}"

    def _get_events_url_for_year(self, year: int) -> str:
        """Get the events URL for a specific year."""
        season_id = self.SEASON_IDS.get(year, self.SEASON_IDS.get(2025, 286))
        return f"https://asjjf.org/main/eventsBySeason/{season_id}"

    @property
    def login_url(self) -> str:
        return "https://asjjf.org/login"

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

    async def _check_logged_in(self, page: NotteSession) -> bool:
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

    async def _login(self, page: NotteSession, context: NotteContext) -> bool:
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

    async def _scrape_events_page(
        self,
        page: NotteSession,
        location: Optional[str] = None,
        date_from: Optional[str] = None,
        date_to: Optional[str] = None
    ) -> List[Tournament]:
        """Scrape tournaments from ASJJF events calendar page.

        Location can be a single country or comma-separated list (e.g., "Malaysia,Taiwan")
        Note: date_from and date_to are accepted but not used (ASJJF doesn't have date filters)
        """
        tournaments = []

        # Parse comma-separated countries for filtering
        target_countries = []
        if location:
            target_countries = [c.strip().lower() for c in location.split(',') if c.strip()]

        try:
            # Determine the correct season URL based on date_from
            events_url = self.events_url
            if date_from:
                try:
                    year = int(date_from.split('-')[0])
                    events_url = self._get_events_url_for_year(year)
                    print(f"[ASJJF] Using {year} season URL based on date_from")
                except (ValueError, IndexError):
                    pass

            print(f"[ASJJF] Navigating to {events_url}")
            await page.goto(events_url, wait_until='domcontentloaded')
            await page.wait_for_timeout(3000)
            print(f"[ASJJF] Page loaded, current URL: {page.url}")

            # Scroll to load all events
            for _ in range(3):
                await page.evaluate('window.scrollTo(0, document.body.scrollHeight)')
                await page.wait_for_timeout(1500)

            content = await page.content()
            soup = BeautifulSoup(content, 'lxml')

            # ASJJF event links follow the pattern /main/eventInfo/[ID]
            event_links = soup.select('a[href*="/main/eventInfo/"]')
            print(f"[ASJJF] Found {len(event_links)} event links")

            seen_hrefs = set()
            for link in event_links:
                href = link.get('href', '')
                if href in seen_hrefs:
                    continue
                seen_hrefs.add(href)

                try:
                    # Get the event name from the link text
                    name = link.get_text(strip=True)
                    if not name or len(name) < 3:
                        continue

                    # Build full URL
                    if href.startswith('/'):
                        registration_link = self.base_url + href
                    else:
                        registration_link = href

                    # Find parent container for additional info
                    parent = link.find_parent(['div', 'tr', 'li', 'article'])
                    parent_text = parent.get_text(separator=' ', strip=True) if parent else name

                    # Extract date - look for patterns like "December 20-21" or "February 28 (Saturday)"
                    date = "TBD"
                    date_match = re.search(r'(January|February|March|April|May|June|July|August|September|October|November|December)\s+(\d{1,2})(?:\s*[-–&]\s*\d{1,2})?(?:,?\s*(\d{4}))?', parent_text, re.IGNORECASE)
                    if date_match:
                        month_name = date_match.group(1)
                        day = date_match.group(2)
                        year = date_match.group(3)
                        if not year:
                            # Assume current or next year
                            year = str(datetime.now().year)
                            # If month is in the past, use next year
                            month_map = {'january': 1, 'february': 2, 'march': 3, 'april': 4, 'may': 5, 'june': 6,
                                        'july': 7, 'august': 8, 'september': 9, 'october': 10, 'november': 11, 'december': 12}
                            event_month = month_map.get(month_name.lower(), 1)
                            if event_month < datetime.now().month:
                                year = str(datetime.now().year + 1)
                        month_map = {'january': 1, 'february': 2, 'march': 3, 'april': 4, 'may': 5, 'june': 6,
                                    'july': 7, 'august': 8, 'september': 9, 'october': 10, 'november': 11, 'december': 12}
                        month_num = month_map.get(month_name.lower(), 1)
                        date = f"{year}-{month_num:02d}-{int(day):02d}"

                    # Extract location/country from event name or parent text
                    # ASJJF events often have country in the name like "Taiwan International", "Tokyo Spring"
                    location_str = "TBD"
                    country = None

                    # Check for countries/cities in the event name
                    country_keywords = {
                        'taiwan': 'Taiwan',
                        'japan': 'Japan',
                        'tokyo': 'Japan',
                        'osaka': 'Japan',
                        'sendai': 'Japan',
                        'nagoya': 'Japan',
                        'china': 'China',
                        'korea': 'South Korea',
                        'philippines': 'Philippines',
                        'malaysia': 'Malaysia',
                        'singapore': 'Singapore',
                        'guam': 'Guam',
                        'asia': 'Asia',
                    }

                    name_lower = name.lower()
                    for keyword, country_name in country_keywords.items():
                        if keyword in name_lower:
                            country = country_name
                            location_str = country_name
                            break

                    # Filter by target countries if specified
                    if target_countries:
                        name_text = f"{name} {location_str}".lower()
                        matches = any(c in name_text for c in target_countries)
                        if not matches:
                            continue

                    city, parsed_country = self._parse_location(location_str)
                    if not country:
                        country = parsed_country

                    tournament = Tournament(
                        id=self._generate_id(name, date),
                        name=name,
                        date=date,
                        location=location_str,
                        city=city,
                        country=country,
                        description=None,
                        organizer="ASJJF",
                        fees=None,
                        registration_link=registration_link,
                        source=self.source,
                        sport="BJJ/Judo",
                    )
                    tournaments.append(tournament)
                    print(f"[ASJJF] Added: {name[:40]}... ({country or 'Unknown'})")

                except Exception as e:
                    print(f"[ASJJF] Error parsing event link: {e}")
                    continue

            print(f"[ASJJF] Successfully scraped {len(tournaments)} tournaments")

        except Exception as e:
            print(f"[ASJJF] Error scraping events: {e}")
            import traceback
            traceback.print_exc()

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
