import re
from typing import List, Optional
from datetime import datetime, timedelta
from bs4 import BeautifulSoup

from .base_agent import BaseTournamentAgent
from ..models import Tournament, TournamentSource
from ..browser.manager import NotteSession, NotteContext


class IBJJFAgent(BaseTournamentAgent):
    """Agent for scraping tournaments from IBJJF using Notte AI."""

    @property
    def source(self) -> TournamentSource:
        return TournamentSource.IBJJF

    @property
    def base_url(self) -> str:
        return "https://ibjjf.com"

    @property
    def events_url(self) -> str:
        return "https://ibjjf.com/events/championships"

    @property
    def login_url(self) -> str:
        return "https://ibjjf.com/login"

    @property
    def email_env_var(self) -> str:
        return "IBJJF_EMAIL"

    @property
    def password_env_var(self) -> str:
        return "IBJJF_PASSWORD"

    @property
    def requires_login(self) -> bool:
        """IBJJF events page is public, no login needed."""
        return False

    async def _check_logged_in(self, page: NotteSession) -> bool:
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

    async def _login(self, page: NotteSession, context: NotteContext) -> bool:
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

    async def _scrape_events_page(
        self,
        page: NotteSession,
        location: Optional[str] = None,
        date_from: Optional[str] = None,
        date_to: Optional[str] = None
    ) -> List[Tournament]:
        """Scrape tournaments from IBJJF championships page.

        Location can be a single country or comma-separated list (e.g., "Malaysia,Taiwan")
        Uses the "Search By" bar to search for each country.
        Note: date_from and date_to are accepted but not used (IBJJF doesn't have date filters)
        """
        tournaments = []
        seen_ids = set()

        # Parse comma-separated countries for searching
        target_countries = []
        if location:
            target_countries = [c.strip() for c in location.split(',') if c.strip()]

        try:
            print(f"[IBJJF] Navigating to {self.events_url}")
            await page.goto(self.events_url, wait_until='domcontentloaded')
            await page.wait_for_timeout(3000)
            print(f"[IBJJF] Page loaded, current URL: {page.url}")

            # If we have target countries, search for each one
            if target_countries:
                for country in target_countries:
                    print(f"[IBJJF] Searching for country: {country}")

                    # Find and use the search bar
                    search_selectors = [
                        'input[type="text"]',
                        'input[type="search"]',
                        'input[placeholder*="search" i]',
                        'input[placeholder*="Search" i]',
                        '.search-input',
                        '#search',
                    ]

                    search_input = None
                    for selector in search_selectors:
                        try:
                            elem = await page.query_selector(selector)
                            if elem:
                                search_input = elem
                                print(f"[IBJJF] Found search input with selector: {selector}")
                                break
                        except Exception:
                            continue

                    if search_input:
                        # Clear and type country name
                        await search_input.click()
                        await page.wait_for_timeout(300)
                        await search_input.fill('')  # Clear existing text
                        await page.keyboard.type(country, delay=50)
                        print(f"[IBJJF] Typed '{country}' in search bar")
                        await page.wait_for_timeout(2000)  # Wait for results to filter

                        # Parse events from current view
                        country_tournaments = await self._parse_events_from_page(page, country)
                        for t in country_tournaments:
                            if t.id not in seen_ids:
                                seen_ids.add(t.id)
                                tournaments.append(t)
                                print(f"[IBJJF] Added: {t.name[:40]}... ({t.location})")

                        # Clear search for next country
                        await search_input.fill('')
                        await page.wait_for_timeout(1000)
                    else:
                        print(f"[IBJJF] Could not find search input, scraping all events")
                        all_tournaments = await self._parse_events_from_page(page, country)
                        # Filter by country name in location/name
                        for t in all_tournaments:
                            if t.id not in seen_ids:
                                t_text = f"{t.name} {t.location}".lower()
                                if country.lower() in t_text:
                                    seen_ids.add(t.id)
                                    tournaments.append(t)
            else:
                # No location filter - scrape all events
                print(f"[IBJJF] No location filter, scraping all events")
                tournaments = await self._parse_events_from_page(page, None)

            print(f"[IBJJF] Successfully scraped {len(tournaments)} tournaments")

        except Exception as e:
            print(f"[IBJJF] Error scraping events: {e}")
            import traceback
            traceback.print_exc()

        return tournaments

    async def _parse_events_from_page(self, page: NotteSession, target_country: Optional[str] = None) -> List[Tournament]:
        """Parse event cards from the current page view."""
        tournaments = []

        try:
            # Scroll to load more events
            for _ in range(2):
                await page.evaluate('window.scrollTo(0, document.body.scrollHeight)')
                await page.wait_for_timeout(1000)

            content = await page.content()
            soup = BeautifulSoup(content, 'lxml')

            # IBJJF shows event cards with images, dates, and locations
            # Look for card containers - they typically link to /events/championships/XXX
            event_links = soup.select('a[href*="/events/championships/"]')

            seen_hrefs = set()
            for link in event_links:
                href = link.get('href', '')
                if href in seen_hrefs:
                    continue
                seen_hrefs.add(href)

                # Find the card container (parent element with date and location info)
                card = link.find_parent(['div', 'article', 'section'])
                if not card:
                    card = link

                try:
                    tournament = self._parse_event_card(card, href, target_country)
                    if tournament:
                        tournaments.append(tournament)
                except Exception as e:
                    print(f"[IBJJF] Error parsing event card: {e}")
                    continue

        except Exception as e:
            print(f"[IBJJF] Error parsing events from page: {e}")

        return tournaments

    def _parse_event_card(self, card, href: str, target_country: Optional[str] = None) -> Optional[Tournament]:
        """Parse an IBJJF event card into a Tournament object.

        Card structure typically includes:
        - Event name/logo image with alt text
        - Date range (e.g., "Dec 11 - Dec 13")
        - Location (e.g., "Las Vegas - NV")
        """
        try:
            card_text = card.get_text(separator=' ', strip=True)

            # Extract event name from image alt text or link text
            name = None
            img = card.select_one('img')
            if img and img.get('alt'):
                name = img['alt'].strip()
                # Clean up common suffixes
                name = re.sub(r'\s*logo\s*$', '', name, flags=re.IGNORECASE)

            if not name:
                # Try to get from link text or title
                link = card.select_one('a')
                if link:
                    name = link.get('title') or link.get_text(strip=True)

            if not name or len(name) < 3:
                # Try to extract from card text
                # Look for championship names like "WORLD JIU-JITSU", "EUROPEAN JIU-JITSU", etc.
                name_match = re.search(r'(WORLD|EUROPEAN|PAN|ASIAN|AMERICAN|KIDS|MASTERS)\s+[A-Z\s\-]+(?:CHAMPIONSHIP|OPEN)?', card_text, re.IGNORECASE)
                if name_match:
                    name = name_match.group(0).strip()

            if not name:
                return None

            # Extract date - look for patterns like "Dec 11 - Dec 13" or "Jan 15* - Jan 24"
            date_match = re.search(r'(Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)\s+(\d{1,2})\*?\s*[-–]\s*(Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)?\s*(\d{1,2})', card_text, re.IGNORECASE)
            if date_match:
                start_month = date_match.group(1)
                start_day = date_match.group(2)
                # Assume current or next year for IBJJF events
                year = datetime.now().year
                # If month is before current month, use next year
                month_map = {'jan': 1, 'feb': 2, 'mar': 3, 'apr': 4, 'may': 5, 'jun': 6,
                             'jul': 7, 'aug': 8, 'sep': 9, 'oct': 10, 'nov': 11, 'dec': 12}
                event_month = month_map.get(start_month.lower(), 1)
                if event_month < datetime.now().month:
                    year += 1
                date = f"{year}-{event_month:02d}-{int(start_day):02d}"
            else:
                date = "TBD"

            # Extract location - look for pattern like "Las Vegas - NV" or "City - State/Country"
            # Location usually comes after the date
            location = "TBD"
            loc_match = re.search(r'([A-Za-z\s]+)\s*[-–]\s*([A-Za-z]{2,})', card_text)
            if loc_match:
                city = loc_match.group(1).strip()
                state_country = loc_match.group(2).strip()
                # Filter out date-like matches
                if city.lower() not in ['jan', 'feb', 'mar', 'apr', 'may', 'jun', 'jul', 'aug', 'sep', 'oct', 'nov', 'dec']:
                    location = f"{city}, {state_country}"

            # Build full URL
            if href.startswith('/'):
                registration_link = self.base_url + href
            else:
                registration_link = href

            # Parse location components
            city, state, country = self._parse_location(location)

            # If target_country was searched, use it as country if we couldn't parse one
            if target_country and not country:
                country = target_country

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
            print(f"[IBJJF] Error parsing event card: {e}")
            return None

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
        """Return empty list - no mock data."""
        return []
