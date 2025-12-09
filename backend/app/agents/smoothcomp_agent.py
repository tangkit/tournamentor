import re
from typing import List, Optional
from datetime import datetime, timedelta
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
        """Apply country filter on Smoothcomp events page using tag-based input.

        Supports multiple countries passed as comma-separated string (e.g., "Malaysia,Taiwan")
        """
        try:
            # Parse comma-separated countries
            countries = [c.strip() for c in location.split(',') if c.strip()]
            print(f"[Smoothcomp] === APPLYING COUNTRY FILTER (TAGS INPUT) ===")
            print(f"[Smoothcomp] Looking for countries: {countries}")

            # Wait for page to be fully loaded
            await page.wait_for_timeout(2000)

            # Strategy: Find the country filter by looking for text "Countries" label
            # then click the input field within that filter section
            try:
                # Method 1: Look for the country filter section by finding "Countries" text
                # and then clicking the nearby input
                country_filter_found = False

                # Try to find by label text - Smoothcomp shows filter labels
                # Look for a container with "Countries" text, then find input within it
                filter_sections = await page.query_selector_all('div.multiselect, div[class*="filter"], div[class*="select"]')
                print(f"[Smoothcomp] Found {len(filter_sections)} potential filter sections")

                for section in filter_sections:
                    section_text = await section.inner_text()
                    if 'countries' in section_text.lower() or 'country' in section_text.lower():
                        print(f"[Smoothcomp] Found country filter section")
                        # Find input within this section
                        input_elem = await section.query_selector('input')
                        if input_elem:
                            await input_elem.click()
                            country_filter_found = True
                            print(f"[Smoothcomp] Clicked country input field")
                            break

                # Method 2: Try finding by placeholder that specifically mentions countries
                if not country_filter_found:
                    # Try various country-specific selectors
                    country_selectors = [
                        'input[placeholder*="countr" i]',
                        'input[aria-label*="countr" i]',
                        'div:has-text("Countries") input',
                        'label:has-text("Countries") + div input',
                        'label:has-text("Countries") ~ div input',
                    ]

                    for selector in country_selectors:
                        try:
                            elem = await page.query_selector(selector)
                            if elem:
                                await elem.click()
                                country_filter_found = True
                                print(f"[Smoothcomp] Found country input with selector: {selector}")
                                break
                        except Exception:
                            continue

                # Method 3: Use locator with text matching
                if not country_filter_found:
                    try:
                        # Find element containing "Countries" text, then find input
                        countries_label = page.locator('text=Countries').first
                        parent = countries_label.locator('xpath=ancestor::div[contains(@class, "multiselect") or contains(@class, "filter")]').first
                        input_elem = parent.locator('input').first
                        await input_elem.click()
                        country_filter_found = True
                        print(f"[Smoothcomp] Found country input via locator")
                    except Exception:
                        pass

                if not country_filter_found:
                    print(f"[Smoothcomp] Could not find country filter input")
                    return False

                # Loop through each country and add it as a tag
                for country in countries:
                    await page.wait_for_timeout(500)

                    # Type the country name
                    await page.keyboard.type(country, delay=50)
                    print(f"[Smoothcomp] Typed '{country}'")
                    await page.wait_for_timeout(1500)

                    # Look for dropdown option that matches and click it directly
                    # This is safer than pressing Enter which might select wrong option
                    dropdown_selectors = [
                        f'li:has-text("{country}")',
                        f'div[class*="option"]:has-text("{country}")',
                        f'span:has-text("{country}")',
                        f'[class*="dropdown"] *:has-text("{country}")',
                    ]

                    option_clicked = False
                    for selector in dropdown_selectors:
                        try:
                            option = await page.query_selector(selector)
                            if option:
                                await option.click()
                                option_clicked = True
                                print(f"[Smoothcomp] Clicked dropdown option for '{country}'")
                                break
                        except Exception:
                            continue

                    # Fallback: if no dropdown option found, press Escape
                    if not option_clicked:
                        await page.keyboard.press('Escape')
                        print(f"[Smoothcomp] Pressed Escape (no option found for '{country}')")

                    await page.wait_for_timeout(1000)

                # Press Escape to ensure dropdown is closed
                await page.keyboard.press('Escape')
                await page.wait_for_timeout(1000)

                print(f"[Smoothcomp] Country filter applied for: {countries}")
                return True

            except Exception as e:
                print(f"[Smoothcomp] Could not interact with country filter: {e}")
                return False

        except Exception as e:
            print(f"[Smoothcomp] Country filter error: {e}")
            return False

    async def _scrape_events_page(self, page: Page, location: Optional[str] = None) -> List[Tournament]:
        """Scrape tournaments from Smoothcomp events page, clicking into each for details.

        Location can be a single country or comma-separated list (e.g., "Malaysia,Taiwan")
        """
        tournaments = []

        # Parse comma-separated countries for filtering
        target_countries = []
        if location:
            target_countries = [c.strip().lower() for c in location.split(',') if c.strip()]

        try:
            # Navigate to events page (URL params don't work well with multiple countries)
            url = self.events_url

            print(f"[Smoothcomp] Navigating to {url}")
            await page.goto(url, wait_until='domcontentloaded')
            await page.wait_for_timeout(3000)
            print(f"[Smoothcomp] Page loaded, current URL: {page.url}")

            # Apply country filter using the dropdown/tag input
            if location:
                print(f"[Smoothcomp] Applying country filter for: {target_countries}")
                await self._apply_country_filter(page, location)

            # Scroll to load more events
            print("[Smoothcomp] Scrolling to load more events...")
            for i in range(3):
                await page.evaluate('window.scrollTo(0, document.body.scrollHeight)')
                await page.wait_for_timeout(1500)

            # Get page content and find event links
            content = await page.content()
            soup = BeautifulSoup(content, 'lxml')

            # Find all event cards/links and pre-filter by location shown on card
            event_links = soup.select('a[href*="/en/event/"]')
            unique_urls = []
            seen = set()

            for link in event_links:
                href = link.get('href', '')
                if href and '/en/event/' in href:
                    event_id = href.split('/en/event/')[-1].split('/')[0]
                    if event_id and event_id not in seen:
                        # Check if this event card mentions any of the target countries
                        # Look at parent container for location text
                        if target_countries:
                            parent = link.find_parent(['div', 'article', 'li', 'section'])
                            if parent:
                                card_text = parent.get_text(separator=' ', strip=True).lower()
                                # Check if ANY of the target countries is in the card
                                country_found = any(country in card_text for country in target_countries)
                                if not country_found:
                                    continue  # Skip this event - doesn't match any target country
                                matched = [c for c in target_countries if c in card_text]
                                print(f"[Smoothcomp] Found event card mentioning: {matched}")

                        seen.add(event_id)
                        if href.startswith('/'):
                            full_url = self.base_url + href
                        else:
                            full_url = href
                        unique_urls.append(full_url)

            print(f"[Smoothcomp] Found {len(unique_urls)} events matching '{target_countries or 'all locations'}'")

            if target_countries and len(unique_urls) == 0:
                print(f"[Smoothcomp] WARNING: No events found for '{target_countries}' on listing page")
                print(f"[Smoothcomp] The country filter may not have worked. Check if countries are spelled correctly.")

            # Limit to first 20 events to avoid too many requests
            max_events = 20
            urls_to_scrape = unique_urls[:max_events]
            print(f"[Smoothcomp] Scraping details for {len(urls_to_scrape)} events...")

            for i, url in enumerate(urls_to_scrape):
                try:
                    print(f"[Smoothcomp] [{i+1}/{len(urls_to_scrape)}] Scraping {url}")
                    tournament = await self._scrape_event_detail(page, url, target_location=location)
                    if tournament:
                        # We already pre-filtered at card level, so trust that filter
                        # Just add the tournament
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

    async def _scrape_event_detail(self, page: Page, url: str, target_location: Optional[str] = None) -> Optional[Tournament]:
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

            # Extract location - look for structured location data
            location = "TBD"

            # First, look for location in structured HTML elements
            # Smoothcomp often has location in specific sections
            location_selectors = [
                '[class*="location"]',
                '[class*="venue"]',
                '[class*="address"]',
                'address',
            ]
            for sel in location_selectors:
                loc_elem = soup.select_one(sel)
                if loc_elem:
                    loc_text = loc_elem.get_text(separator=', ', strip=True)
                    # Filter out nav/menu text
                    if loc_text and len(loc_text) < 200 and 'Smoothcomp' not in loc_text and 'Contact' not in loc_text:
                        location = loc_text
                        print(f"[Smoothcomp] Found location from element {sel}: '{location[:50]}...'")
                        break

            # If no structured location, try regex on page text after "Location" heading
            if location == "TBD":
                # Look for text after "Location" header
                loc_match = re.search(r'Location\s+([A-Z][^,]+(?:,\s*[A-Z][^,]+){0,3})', page_text)
                if loc_match:
                    location = loc_match.group(1).strip()[:100]  # Limit length
                    print(f"[Smoothcomp] Found location from 'Location' header: '{location}'")

            # Try to find City, Country pattern
            if location == "TBD":
                countries = ['Malaysia', 'Singapore', 'Indonesia', 'Thailand', 'Philippines', 'Australia', 'Japan', 'USA', 'United States', 'India', 'Hong Kong', 'South Korea', 'United Kingdom', 'UK', 'Canada', 'New Zealand', 'Brazil']
                for country in countries:
                    if country.lower() in page_text.lower():
                        # Find city before country name
                        pattern = rf'([A-Z][a-zA-Z\s]+(?:,\s*[A-Z][a-zA-Z\s]+)?),?\s*{country}'
                        match = re.search(pattern, page_text)
                        if match:
                            location = f"{match.group(1).strip()}, {country}"
                            print(f"[Smoothcomp] Found location from country pattern: '{location}'")
                            break
                        else:
                            location = country
                            print(f"[Smoothcomp] Using just country: '{location}'")

            # Extract organizer - look for "Organizer & merchant" section
            organizer = None
            # Look for pattern like "Grappling Industries Malaysia" before "year on Smoothcomp"
            org_match = re.search(r'(?:Organizer|merchant)[^A-Za-z]*([A-Z][A-Za-z]+(?:\s+[A-Z][a-z]+)+)(?:\s*\d|\s+year|\s+event)', page_text)
            if org_match:
                organizer = org_match.group(1).strip()

            # Alternative: look for organization name pattern before "on Smoothcomp"
            if not organizer:
                org_match = re.search(r'([A-Z][A-Za-z]+(?:\s+[A-Z][a-z]+){1,4})\s+\d+\s+year', page_text)
                if org_match:
                    organizer = org_match.group(1).strip()

            # Filter out common false positives
            if organizer and organizer.lower() in ['cancel', 'download', 'accept', 'submit', 'register', 'login', 'sign']:
                organizer = None

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
            print(f"[Smoothcomp] === DATE EXTRACTION DEBUG ===")

            # Look for "Event dates" followed by date - Smoothcomp shows this as a header
            # Pattern: "Event dates 10 Jan - 11 Jan" or "Event dates 10 January 2026"
            date_match = re.search(r'Event\s+dates?\s*[:\s]*(\d{1,2}\s+(?:Jan(?:uary)?|Feb(?:ruary)?|Mar(?:ch)?|Apr(?:il)?|May|Jun(?:e)?|Jul(?:y)?|Aug(?:ust)?|Sep(?:tember)?|Oct(?:ober)?|Nov(?:ember)?|Dec(?:ember)?)[a-z]*(?:\s*[-–&]\s*\d{1,2}\s+(?:Jan(?:uary)?|Feb(?:ruary)?|Mar(?:ch)?|Apr(?:il)?|May|Jun(?:e)?|Jul(?:y)?|Aug(?:ust)?|Sep(?:tember)?|Oct(?:ober)?|Nov(?:ember)?|Dec(?:ember)?)[a-z]*)?)(?:\s*,?\s*(\d{4}))?', page_text, re.IGNORECASE)
            if date_match:
                date_str = date_match.group(1)
                year = date_match.group(2)
                if year:
                    date_str = f"{date_str} {year}"
                print(f"[Smoothcomp] Found 'Event dates' pattern: '{date_str}'")

            # If no match, look for standalone date patterns
            if not date_str:
                # Look for "10 Jan 2026" or "10 January 2026" pattern
                date_match = re.search(r'(\d{1,2})\s+(Jan(?:uary)?|Feb(?:ruary)?|Mar(?:ch)?|Apr(?:il)?|May|Jun(?:e)?|Jul(?:y)?|Aug(?:ust)?|Sep(?:tember)?|Oct(?:ober)?|Nov(?:ember)?|Dec(?:ember)?)[a-z]*\s+(\d{4})', page_text, re.IGNORECASE)
                if date_match:
                    date_str = date_match.group(0)
                    print(f"[Smoothcomp] Found 'DD Mon YYYY' pattern: '{date_str}'")

            if not date_str:
                # Look for "January 10, 2026" pattern
                date_match = re.search(r'(Jan(?:uary)?|Feb(?:ruary)?|Mar(?:ch)?|Apr(?:il)?|May|Jun(?:e)?|Jul(?:y)?|Aug(?:ust)?|Sep(?:tember)?|Oct(?:ober)?|Nov(?:ember)?|Dec(?:ember)?)\s+(\d{1,2})(?:\s*[&,-]\s*\d{1,2})?,?\s*(\d{4})', page_text, re.IGNORECASE)
                if date_match:
                    date_str = date_match.group(0)
                    print(f"[Smoothcomp] Found 'Month DD, YYYY' pattern: '{date_str}'")

            if not date_str:
                # Last resort: look for any "10 Jan" without year (assume current/next year)
                date_match = re.search(r'(\d{1,2})\s+(Jan(?:uary)?|Feb(?:ruary)?|Mar(?:ch)?|Apr(?:il)?|May|Jun(?:e)?|Jul(?:y)?|Aug(?:ust)?|Sep(?:tember)?|Oct(?:ober)?|Nov(?:ember)?|Dec(?:ember)?)', page_text, re.IGNORECASE)
                if date_match:
                    date_str = date_match.group(0)
                    print(f"[Smoothcomp] Found 'DD Mon' pattern without year: '{date_str}'")

            if not date_str:
                print(f"[Smoothcomp] No date pattern found in page text")
                # Debug: print a snippet that might contain the date
                if 'Event' in page_text:
                    idx = page_text.find('Event')
                    snippet = page_text[max(0, idx):min(len(page_text), idx+200)]
                    print(f"[Smoothcomp] Text near 'Event': '{snippet}'")

            date = self._parse_date(date_str) if date_str else "TBD"
            print(f"[Smoothcomp] Final parsed date: '{date}'")

            # Parse location components
            city, state, country = self._parse_location(location)

            # If we have target countries and any is found in page text, use it as country
            # This helps when location extraction fails to get proper country
            if target_location:
                # Parse comma-separated target countries
                target_countries = [c.strip() for c in target_location.split(',') if c.strip()]
                page_text_lower = page_text.lower()
                for target_country in target_countries:
                    if target_country.lower() in page_text_lower:
                        if not country or country == location:  # country wasn't properly parsed
                            country = target_country
                            print(f"[Smoothcomp] Set country to target: '{country}'")
                        # Also update location string if it's generic
                        if location == "TBD" or "Location" in location:
                            location = target_country
                            print(f"[Smoothcomp] Updated location to: '{location}'")
                        break  # Use first matching country

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

        print(f"[Smoothcomp] _parse_date input: '{date_str}'")

        # Clean the date string - normalize spaces and dashes
        date_str = re.sub(r'\s+', ' ', date_str).strip()
        # Remove range part (e.g., "10 Jan - 11 Jan" -> "10 Jan")
        date_str = re.split(r'\s*[-–&]\s*\d', date_str)[0].strip()
        print(f"[Smoothcomp] _parse_date cleaned: '{date_str}'")

        # Try various date formats with year
        formats_with_year = [
            "%Y-%m-%d",
            "%d %B %Y",      # 10 January 2026
            "%d %b %Y",      # 10 Jan 2026
            "%B %d, %Y",     # January 10, 2026
            "%b %d, %Y",     # Jan 10, 2026
            "%B %d %Y",      # January 10 2026
            "%b %d %Y",      # Jan 10 2026
            "%Y %B %d",      # 2026 January 10
            "%Y %b %d",      # 2026 Jan 10
            "%d/%m/%Y",
            "%m/%d/%Y",
        ]

        for fmt in formats_with_year:
            try:
                parsed = datetime.strptime(date_str, fmt)
                result = parsed.strftime("%Y-%m-%d")
                print(f"[Smoothcomp] Parsed with format '{fmt}': {result}")
                return result
            except ValueError:
                continue

        # Try formats WITHOUT year - assume current year or next year if date has passed
        formats_no_year = [
            "%d %B",         # 10 January
            "%d %b",         # 10 Jan
            "%B %d",         # January 10
            "%b %d",         # Jan 10
        ]

        current_year = datetime.now().year
        for fmt in formats_no_year:
            try:
                parsed = datetime.strptime(date_str, fmt)
                # Use current year, but if date is in the past, use next year
                parsed = parsed.replace(year=current_year)
                if parsed < datetime.now() - timedelta(days=30):  # 30 day grace period
                    parsed = parsed.replace(year=current_year + 1)
                result = parsed.strftime("%Y-%m-%d")
                print(f"[Smoothcomp] Parsed with format '{fmt}' (no year): {result}")
                return result
            except ValueError:
                continue

        # Try to extract date with regex for numeric formats
        match = re.search(r'(\d{1,2})[/\-.](\d{1,2})[/\-.](\d{2,4})', date_str)
        if match:
            day, month, year = match.groups()
            if len(year) == 2:
                year = "20" + year
            result = f"{year}-{month.zfill(2)}-{day.zfill(2)}"
            print(f"[Smoothcomp] Parsed with numeric regex: {result}")
            return result

        print(f"[Smoothcomp] Could not parse date: '{date_str}'")
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
        """Return empty list - no mock data."""
        return []
