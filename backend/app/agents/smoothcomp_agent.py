import re
from typing import List, Optional
from datetime import datetime, timedelta
import random
from playwright.async_api import Page, BrowserContext
from bs4 import BeautifulSoup

from .base_agent import BaseTournamentAgent
from ..models import Tournament, TournamentSource
from ..browser.manager import BrowserManager


class SmoothcompAgent(BaseTournamentAgent):
    """Agent for scraping tournaments from Smoothcomp using Playwright."""

    @property
    def source(self) -> TournamentSource:
        return TournamentSource.SMOOTHCOMP

    @property
    def base_url(self) -> str:
        return "https://smoothcomp.com"

    @property
    def events_url(self) -> str:
        return "https://smoothcomp.com/en/events"

    @property
    def login_url(self) -> str:
        return "https://smoothcomp.com/en/login"

    @property
    def email_env_var(self) -> str:
        return "SMOOTHCOMP_EMAIL"

    @property
    def password_env_var(self) -> str:
        return "SMOOTHCOMP_PASSWORD"

    @property
    def requires_login(self) -> bool:
        """Smoothcomp events page is public, no login needed."""
        return False

    async def _check_logged_in(self, page: Page) -> bool:
        """Check if already logged in to Smoothcomp."""
        try:
            await page.goto(self.base_url, wait_until='domcontentloaded')
            await page.wait_for_timeout(2000)

            # Check for user menu/profile indicator
            logged_in_selectors = [
                '[data-testid="user-menu"]',
                '.user-dropdown',
                '.profile-menu',
                'a[href*="/profile"]',
                'a[href*="/logout"]',
                '.nav-user',
            ]

            for selector in logged_in_selectors:
                element = await page.query_selector(selector)
                if element:
                    return True

            # Check if login button is present (means not logged in)
            login_button = await page.query_selector('a[href*="/login"]')
            if login_button:
                return False

            return False
        except Exception as e:
            print(f"Error checking login status: {e}")
            return False

    async def _login(self, page: Page, context: BrowserContext) -> bool:
        """Login to Smoothcomp."""
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
                'input[placeholder*="email" i]',
            ]

            password_selectors = [
                'input[name="password"]',
                'input[type="password"]',
                '#password',
            ]

            # Find and fill email
            for selector in email_selectors:
                try:
                    await page.wait_for_selector(selector, timeout=5000)
                    await page.fill(selector, email)
                    break
                except Exception:
                    continue

            # Find and fill password
            for selector in password_selectors:
                try:
                    await page.wait_for_selector(selector, timeout=5000)
                    await page.fill(selector, password)
                    break
                except Exception:
                    continue

            # Submit login form
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

            # Wait for navigation after login
            await page.wait_for_timeout(3000)
            await page.wait_for_load_state('networkidle', timeout=10000)

            # Verify login success
            logged_in = await self._check_logged_in(page)
            if logged_in:
                await self._save_session(context)
                return True

            return False

        except Exception as e:
            print(f"Login error: {e}")
            return False

    async def _scrape_events_page(self, page: Page, location: Optional[str] = None) -> List[Tournament]:
        """Scrape tournaments from Smoothcomp events page."""
        tournaments = []

        try:
            print(f"[Smoothcomp] Navigating to {self.events_url}")
            await page.goto(self.events_url, wait_until='domcontentloaded')
            await page.wait_for_timeout(3000)
            print(f"[Smoothcomp] Page loaded, current URL: {page.url}")

            # Scroll to load more events
            print("[Smoothcomp] Scrolling to load more events...")
            for i in range(3):
                await page.evaluate('window.scrollTo(0, document.body.scrollHeight)')
                await page.wait_for_timeout(1500)
                print(f"[Smoothcomp] Scroll {i+1}/3 complete")

            # Get page content
            content = await page.content()
            print(f"[Smoothcomp] Got page content, length: {len(content)} chars")
            soup = BeautifulSoup(content, 'lxml')

            # Find event cards/listings
            event_selectors = [
                'div[class*="event-card"]',
                'div[class*="event-item"]',
                'article[class*="event"]',
                '.event-listing',
                '[data-event-id]',
            ]

            events = []
            for selector in event_selectors:
                events = soup.select(selector)
                if events:
                    print(f"[Smoothcomp] Found {len(events)} events with selector: {selector}")
                    break

            # If no specific event containers found, look for links to events
            if not events:
                print("[Smoothcomp] No event containers found, looking for event links...")
                event_links = soup.select('a[href*="/en/event/"]')
                print(f"[Smoothcomp] Found {len(event_links)} event links")
                for link in event_links:
                    parent = link.find_parent(['div', 'article', 'li'])
                    if parent and parent not in events:
                        events.append(parent)
                print(f"[Smoothcomp] Found {len(events)} parent containers")

            print(f"[Smoothcomp] Processing {min(len(events), 50)} events...")
            for event in events[:50]:  # Limit to 50 events
                try:
                    tournament = self._parse_event_element(event)
                    if tournament:
                        # Apply location filter
                        if location:
                            loc_lower = location.lower()
                            if (loc_lower not in tournament.location.lower() and
                                (not tournament.city or loc_lower not in tournament.city.lower()) and
                                (not tournament.country or loc_lower not in tournament.country.lower())):
                                continue
                        tournaments.append(tournament)
                except Exception as e:
                    print(f"[Smoothcomp] Error parsing event: {e}")
                    continue

            print(f"[Smoothcomp] Successfully parsed {len(tournaments)} tournaments")

        except Exception as e:
            print(f"[Smoothcomp] Error scraping events page: {e}")
            import traceback
            traceback.print_exc()

        return tournaments

    def _parse_event_element(self, element) -> Optional[Tournament]:
        """Parse a BeautifulSoup element into a Tournament object."""
        try:
            # Extract event name - try multiple selectors
            name = None
            name_selectors = [
                'h2', 'h3', 'h4',
                '.event-name', '.event-title',
                '[class*="title"]',
                '[class*="name"]',
            ]
            for selector in name_selectors:
                name_elem = element.select_one(selector)
                if name_elem:
                    name = name_elem.get_text(strip=True)
                    if name:
                        break

            if not name:
                link = element.select_one('a[href*="/event/"]')
                if link:
                    name = link.get_text(strip=True)

            if not name:
                return None

            # Extract location - look for text with country pattern (City, Country)
            location = "TBD"
            location_selectors = [
                '[class*="location"]',
                '[class*="venue"]',
                '[class*="place"]',
                '[class*="city"]',
            ]
            for selector in location_selectors:
                loc_elem = element.select_one(selector)
                if loc_elem:
                    location = loc_elem.get_text(strip=True)
                    if location and ',' in location:
                        break

            # If still no location, look for any text containing comma (City, Country pattern)
            if location == "TBD" or ',' not in location:
                all_text = element.get_text(separator='|', strip=True)
                # Look for patterns like "City, Country"
                import re
                loc_match = re.search(r'([A-Za-z\s]+,\s*[A-Za-z\s]+)', all_text)
                if loc_match:
                    potential_loc = loc_match.group(1).strip()
                    # Avoid matching dates or other patterns
                    if not any(month in potential_loc.lower() for month in ['january', 'february', 'march', 'april', 'may', 'june', 'july', 'august', 'september', 'october', 'november', 'december']):
                        location = potential_loc

            # Extract date - look for date patterns
            date_str = None
            date_selectors = [
                '[class*="date"]',
                'time',
                '[class*="when"]',
            ]
            for selector in date_selectors:
                date_elem = element.select_one(selector)
                if date_elem:
                    date_str = date_elem.get_text(strip=True)
                    if date_str:
                        break

            # If no date found, search in text for date pattern
            if not date_str:
                all_text = element.get_text(strip=True)
                # Look for "2026 January 10" or similar patterns
                import re
                date_match = re.search(r'(\d{4}\s+[A-Za-z]+\s+\d{1,2})', all_text)
                if date_match:
                    date_str = date_match.group(1)

            date = self._parse_date(date_str) if date_str else "TBD"

            # Extract registration link
            link_elem = element.select_one('a[href*="/event/"]')
            if link_elem and link_elem.get('href'):
                href = link_elem['href']
                if href.startswith('/'):
                    registration_link = self.base_url + href
                else:
                    registration_link = href
            else:
                registration_link = self.events_url

            # Parse location components
            city, state, country = self._parse_location(location)

            # Debug output for first few events
            print(f"[Smoothcomp] Parsed: name='{name[:30] if name else None}...', location='{location}', date='{date}', country='{country}'")

            return Tournament(
                id=self._generate_id(name, date),
                name=name,
                date=date,
                location=location,
                city=city,
                state=state,
                country=country,
                description=None,
                organizer=None,
                fees=None,
                registration_link=registration_link,
                source=self.source,
                sport="BJJ",
            )

        except Exception as e:
            print(f"[Smoothcomp] Error parsing event element: {e}")
            import traceback
            traceback.print_exc()
            return None

    def _parse_date(self, date_str: str) -> str:
        """Parse date string into YYYY-MM-DD format."""
        if not date_str:
            return "TBD"

        # Try various date formats
        formats = [
            "%Y-%m-%d",
            "%Y %B %d",      # 2026 January 10
            "%Y %b %d",      # 2026 Jan 10
            "%d/%m/%Y",
            "%m/%d/%Y",
            "%B %d, %Y",
            "%b %d, %Y",
            "%d %B %Y",
            "%d %b %Y",
        ]

        # Clean the date string
        date_str = re.sub(r'\s+', ' ', date_str).strip()

        for fmt in formats:
            try:
                parsed = datetime.strptime(date_str, fmt)
                return parsed.strftime("%Y-%m-%d")
            except ValueError:
                continue

        # Try to extract date with regex
        match = re.search(r'(\d{1,2})[/\-.](\d{1,2})[/\-.](\d{2,4})', date_str)
        if match:
            day, month, year = match.groups()
            if len(year) == 2:
                year = "20" + year
            return f"{year}-{month.zfill(2)}-{day.zfill(2)}"

        return "TBD"

    def _parse_location(self, location: str) -> tuple[Optional[str], Optional[str], Optional[str]]:
        """Parse location string into city, state, country components."""
        if not location or location == "TBD":
            return None, None, None

        parts = [p.strip() for p in location.split(',')]

        city = parts[0] if len(parts) > 0 else None
        state = parts[1] if len(parts) > 1 else None
        country = parts[-1] if len(parts) > 2 else (parts[1] if len(parts) > 1 else None)

        return city, state, country

    def _get_mock_data(self) -> List[Tournament]:
        """Return realistic mock data for Smoothcomp tournaments."""
        base_date = datetime.now()

        mock_tournaments = [
            {
                "name": "Austin Open Jiu-Jitsu Championship",
                "city": "Austin",
                "state": "TX",
                "country": "USA",
                "organizer": "Texas Grappling Federation",
                "fees": "$85 - $120",
                "description": "Open weight and absolute divisions. Gi and No-Gi competitions available.",
                "days_offset": 14
            },
            {
                "name": "California State BJJ Championship",
                "city": "Los Angeles",
                "state": "CA",
                "country": "USA",
                "organizer": "SoCal Jiu-Jitsu League",
                "fees": "$95 - $140",
                "description": "IBJJF rules. All belt levels welcome. Kids, teens, and adults divisions.",
                "days_offset": 28
            },
            {
                "name": "Miami Submission Only",
                "city": "Miami",
                "state": "FL",
                "country": "USA",
                "organizer": "Florida Grappling Events",
                "fees": "$75 - $100",
                "description": "Submission only format. No points, no advantages. EBI overtime rules.",
                "days_offset": 35
            },
            {
                "name": "NYC Grappling Grand Prix",
                "city": "New York",
                "state": "NY",
                "country": "USA",
                "organizer": "Northeast Grappling Association",
                "fees": "$90 - $130",
                "description": "Premier Northeast event. Cash prizes for black belt divisions.",
                "days_offset": 42
            },
            {
                "name": "Seattle Judo & BJJ Open",
                "city": "Seattle",
                "state": "WA",
                "country": "USA",
                "organizer": "Pacific Northwest Martial Arts",
                "fees": "$70 - $110",
                "description": "Combined Judo and BJJ tournament. Separate and combined divisions.",
                "days_offset": 56
            },
            {
                "name": "Denver Rocky Mountain Championships",
                "city": "Denver",
                "state": "CO",
                "country": "USA",
                "organizer": "Colorado Grappling Alliance",
                "fees": "$80 - $115",
                "description": "High altitude competition! All skill levels. Gi and No-Gi.",
                "days_offset": 63
            },
            {
                "name": "Chicago Midwest Open",
                "city": "Chicago",
                "state": "IL",
                "country": "USA",
                "organizer": "Midwest BJJ Federation",
                "fees": "$85 - $125",
                "description": "Largest Midwest tournament. Over 1000 competitors expected.",
                "days_offset": 70
            },
            {
                "name": "Vancouver International Grappling",
                "city": "Vancouver",
                "state": "BC",
                "country": "Canada",
                "organizer": "Canadian Grappling Association",
                "fees": "$90 CAD - $130 CAD",
                "description": "International competitors welcome. IBJJF and submission only divisions.",
                "days_offset": 77
            },
        ]

        tournaments = []
        for t in mock_tournaments:
            date = base_date + timedelta(days=t["days_offset"])
            tournament = Tournament(
                id=self._generate_id(t["name"], date.strftime("%Y-%m-%d")),
                name=t["name"],
                date=date.strftime("%Y-%m-%d"),
                end_date=(date + timedelta(days=random.choice([0, 1]))).strftime("%Y-%m-%d"),
                location=f"{t['city']}, {t['state']}, {t['country']}",
                city=t["city"],
                state=t["state"],
                country=t["country"],
                description=t["description"],
                organizer=t["organizer"],
                fees=t["fees"],
                registration_link=f"https://smoothcomp.com/en/event/{self._generate_id(t['name'], '')}",
                source=self.source,
                sport="BJJ/Judo",
                registration_deadline=(date - timedelta(days=7)).strftime("%Y-%m-%d"),
            )
            tournaments.append(tournament)

        return tournaments
