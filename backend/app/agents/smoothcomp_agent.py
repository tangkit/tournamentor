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

    async def _apply_country_filter(self, page: Page, location: str) -> bool:
        """Apply country filter on Smoothcomp events page using their dropdown."""
        try:
            print(f"[Smoothcomp] Applying country filter for: {location}")

            # Wait for page to be fully loaded
            await page.wait_for_timeout(2000)

            # Find and click the "Select countries" dropdown
            # Try multiple selectors for the country dropdown
            dropdown_selectors = [
                'text="Select countries"',
                '[placeholder*="country" i]',
                '[class*="country"]',
                'select',
            ]

            clicked = False
            for selector in dropdown_selectors:
                try:
                    element = await page.query_selector(selector)
                    if element:
                        await element.click()
                        await page.wait_for_timeout(1000)
                        clicked = True
                        print(f"[Smoothcomp] Clicked dropdown with selector: {selector}")
                        break
                except Exception:
                    continue

            if not clicked:
                # Try clicking by text content
                try:
                    await page.click('text="Select countries"')
                    await page.wait_for_timeout(1000)
                    clicked = True
                    print("[Smoothcomp] Clicked 'Select countries' text")
                except Exception:
                    pass

            if clicked:
                # Now type the country name to search/filter
                await page.keyboard.type(location, delay=100)
                await page.wait_for_timeout(1000)

                # Press Enter or click the matching option
                try:
                    # Look for the country in dropdown options
                    option = await page.query_selector(f'text="{location}"')
                    if option:
                        await option.click()
                        print(f"[Smoothcomp] Selected: {location}")
                        await page.wait_for_timeout(2000)
                        return True
                    else:
                        # Try pressing Enter
                        await page.keyboard.press('Enter')
                        await page.wait_for_timeout(2000)
                        return True
                except Exception as e:
                    print(f"[Smoothcomp] Could not select option: {e}")

            # Fallback: Check if URL already filtered or try URL param
            print(f"[Smoothcomp] Dropdown filter may not have worked, continuing anyway...")
            return False

        except Exception as e:
            print(f"[Smoothcomp] Could not apply country filter: {e}")
            return False

    async def _scrape_events_page(self, page: Page, location: Optional[str] = None) -> List[Tournament]:
        """Scrape tournaments from Smoothcomp events page, clicking into each for details."""
        tournaments = []

        try:
            print(f"[Smoothcomp] Navigating to {self.events_url}")
            await page.goto(self.events_url, wait_until='domcontentloaded')
            await page.wait_for_timeout(3000)
            print(f"[Smoothcomp] Page loaded, current URL: {page.url}")

            # If location specified, try to use Smoothcomp's country filter
            if location:
                await self._apply_country_filter(page, location)

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
            page_text = soup.get_text(separator=' ', strip=True)

            # Extract event name from h1 (exclude dates that might be in h1)
            name = None
            h1 = soup.select_one('h1')
            if h1:
                name = h1.get_text(strip=True)
                # Clean up name - remove embedded dates
                name = re.sub(r'\d{1,2}\s+(Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[a-z]*.*$', '', name, flags=re.IGNORECASE).strip()
            if not name:
                title = soup.select_one('title')
                if title:
                    name = title.get_text(strip=True).split(' - ')[0].split('|')[0].strip()
            if not name:
                return None

            # Extract location - look for address with country
            location = "TBD"
            # Look for text after "Location" header that contains address
            loc_match = re.search(r'Petaling Jaya[^,]*,\s*([^,]+,\s*)?Malaysia', page_text, re.IGNORECASE)
            if loc_match:
                location = loc_match.group(0)
            else:
                # Generic pattern: City, State/Province, Country
                loc_match = re.search(r'([A-Z][a-z]+(?:\s+[A-Z][a-z]+)*),?\s*(?:[A-Z][a-z]+(?:\s+[A-Z][a-z]+)*)?,?\s*(Malaysia|Singapore|Indonesia|Thailand|Philippines|Australia|Japan|USA|India|Hong Kong|South Korea|Kazakhstan|United Arab Emirates|Uzbekistan)', page_text)
                if loc_match:
                    location = loc_match.group(0).strip()

            # If still no location, look for "Malaysia" and nearby text
            if location == "TBD":
                countries = ['Malaysia', 'Singapore', 'Indonesia', 'Thailand', 'Philippines', 'Australia', 'Japan', 'USA', 'India', 'Hong Kong']
                for country in countries:
                    if country.lower() in page_text.lower():
                        # Find context around country name
                        match = re.search(rf'([A-Z][a-z]+(?:[\s,]+[A-Z][a-z]+){{0,3}}[\s,]+){country}', page_text, re.IGNORECASE)
                        if match:
                            location = match.group(0).strip()
                            break
                        else:
                            location = country

            # Extract organizer - look for "Organizer" section
            organizer = None
            org_match = re.search(r'Organizer[^:]*[:\s]+([A-Za-z][A-Za-z\s]+?)(?:\d|\bon\b|$)', page_text)
            if org_match:
                organizer = org_match.group(1).strip()
            else:
                # Try to find text after "merchant" or "organizer"
                org_match = re.search(r'(?:merchant|organizer)[:\s]+([A-Za-z][A-Za-z\s]+?)(?:\d|year|event|on\s+Smooth)', page_text, re.IGNORECASE)
                if org_match:
                    organizer = org_match.group(1).strip()

            # Extract fees - look for price patterns with context
            fees = None
            # Look for registration fees like "RM185 - Kids", "$85 - Adults"
            price_matches = re.findall(r'(RM|USD|\$|€|£|SGD|THB|IDR|PHP|AUD|JPY)\s*(\d+(?:,\d{3})*(?:\.\d{2})?)', page_text)
            if price_matches:
                # Convert to numeric for sorting
                prices = []
                for currency, amount in price_matches:
                    try:
                        num = float(amount.replace(',', ''))
                        prices.append((num, f"{currency}{amount}"))
                    except:
                        pass
                if prices:
                    prices.sort(key=lambda x: x[0])
                    if len(prices) > 1:
                        fees = f"{prices[0][1]} - {prices[-1][1]}"
                    else:
                        fees = prices[0][1]

            # Extract date - look for "Event dates" section or date patterns
            date_str = None
            # Look for "Event dates" followed by date
            date_match = re.search(r'Event\s+dates?\s*[:\s]+(\d{1,2}\s+(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[a-z]*)', page_text, re.IGNORECASE)
            if date_match:
                date_str = date_match.group(1)
            else:
                # Look for date pattern with year like "January 10 & 11, 2026"
                date_match = re.search(r'(?:January|February|March|April|May|June|July|August|September|October|November|December)\s+\d{1,2}(?:\s*[&,-]\s*\d{1,2})?,?\s*\d{4}', page_text, re.IGNORECASE)
                if date_match:
                    date_str = date_match.group(0)
                else:
                    # Look for "10 Jan" pattern
                    date_match = re.search(r'(\d{1,2})\s+(Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[a-z]*(?:\s*[-&]\s*\d{1,2}\s+(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[a-z]*)?\s*(?:,?\s*(\d{4}))?', page_text, re.IGNORECASE)
                    if date_match:
                        date_str = date_match.group(0)

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
