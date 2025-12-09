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
        """Scrape tournaments from Smoothcomp events page, clicking into each for details."""
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

            # Get page content and find event links
            content = await page.content()
            soup = BeautifulSoup(content, 'lxml')

            # Find all event links
            event_links = soup.select('a[href*="/en/event/"]')
            unique_urls = []
            seen = set()
            for link in event_links:
                href = link.get('href', '')
                if href and '/en/event/' in href:
                    # Build full URL
                    if href.startswith('/'):
                        full_url = self.base_url + href
                    else:
                        full_url = href
                    # Only add unique event URLs (not subpages)
                    event_id = href.split('/en/event/')[-1].split('/')[0]
                    if event_id and event_id not in seen:
                        seen.add(event_id)
                        unique_urls.append(full_url)

            print(f"[Smoothcomp] Found {len(unique_urls)} unique event URLs")

            # Limit to first 20 events to avoid too many requests
            max_events = 20
            urls_to_scrape = unique_urls[:max_events]
            print(f"[Smoothcomp] Scraping details for {len(urls_to_scrape)} events...")

            for i, url in enumerate(urls_to_scrape):
                try:
                    print(f"[Smoothcomp] [{i+1}/{len(urls_to_scrape)}] Scraping {url}")
                    tournament = await self._scrape_event_detail(page, url)
                    if tournament:
                        # Apply location filter
                        if location:
                            loc_lower = location.lower()
                            if (loc_lower not in tournament.location.lower() and
                                (not tournament.city or loc_lower not in tournament.city.lower()) and
                                (not tournament.country or loc_lower not in tournament.country.lower())):
                                print(f"[Smoothcomp] Skipping - location filter didn't match")
                                continue
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

        return tournaments

    async def _scrape_event_detail(self, page: Page, url: str) -> Optional[Tournament]:
        """Scrape full tournament details from event detail page."""
        try:
            await page.goto(url, wait_until='domcontentloaded')
            await page.wait_for_timeout(2000)

            content = await page.content()
            soup = BeautifulSoup(content, 'lxml')

            # Extract event name from h1 or title
            name = None
            name_elem = soup.select_one('h1, h2, [class*="event-title"], [class*="event-name"]')
            if name_elem:
                name = name_elem.get_text(strip=True)
            if not name:
                title = soup.select_one('title')
                if title:
                    name = title.get_text(strip=True).split(' - ')[0].strip()
            if not name:
                return None

            # Extract location - look for Location section or address
            location = "TBD"
            location_selectors = [
                '[class*="location"] address',
                '[class*="location"]',
                'address',
            ]
            for selector in location_selectors:
                loc_elem = soup.select_one(selector)
                if loc_elem:
                    location = loc_elem.get_text(separator=', ', strip=True)
                    if location and len(location) > 5:
                        break

            # Look for text containing city, country pattern
            if location == "TBD":
                # Try to find location in page text
                page_text = soup.get_text()
                loc_match = re.search(r'Location[:\s]+([^\n]+)', page_text)
                if loc_match:
                    location = loc_match.group(1).strip()

            # Extract organizer
            organizer = None
            org_selectors = [
                '[class*="organizer"]',
                '[class*="merchant"]',
                '[class*="host"]',
            ]
            for selector in org_selectors:
                org_elem = soup.select_one(selector)
                if org_elem:
                    organizer = org_elem.get_text(strip=True)
                    # Clean up organizer name
                    organizer = re.sub(r'\d+\s*(year|event).*$', '', organizer, flags=re.IGNORECASE).strip()
                    if organizer:
                        break

            # Extract fees - look for price patterns (RM, $, €, etc.)
            fees = None
            page_text = soup.get_text()
            # Look for price patterns like "RM185", "$85", "€75", etc.
            price_matches = re.findall(r'(RM|USD|\$|€|£)\s*(\d+(?:\.\d{2})?)', page_text)
            if price_matches:
                prices = sorted(set([f"{m[0]}{m[1]}" for m in price_matches]))
                if len(prices) > 1:
                    fees = f"{prices[0]} - {prices[-1]}"
                elif prices:
                    fees = prices[0]

            # Extract date - look for "Event dates" or date patterns
            date_str = None
            date_selectors = [
                '[class*="event-date"]',
                '[class*="dates"]',
                'time',
            ]
            for selector in date_selectors:
                date_elem = soup.select_one(selector)
                if date_elem:
                    date_str = date_elem.get_text(strip=True)
                    if date_str:
                        break

            # Try to find date in text like "January 10 & 11, 2026" or "10 Jan - 11 Jan"
            if not date_str:
                date_match = re.search(r'(\d{1,2}\s+(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[a-z]*(?:\s*[-&]\s*\d{1,2}\s+(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[a-z]*)?(?:\s*,?\s*\d{4})?)', page_text, re.IGNORECASE)
                if date_match:
                    date_str = date_match.group(1)
                else:
                    # Try "2026 January 10" format
                    date_match = re.search(r'(\d{4}\s+[A-Za-z]+\s+\d{1,2})', page_text)
                    if date_match:
                        date_str = date_match.group(1)

            date = self._parse_date(date_str) if date_str else "TBD"

            # Parse location components
            city, state, country = self._parse_location(location)

            print(f"[Smoothcomp] Detail: name='{name[:30]}...', loc='{location[:30]}...', org='{organizer}', fees='{fees}', date='{date}'")

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
