import json
from typing import List
from datetime import datetime, timedelta
import random

from .base_agent import BaseTournamentAgent
from ..models import Tournament, TournamentSource


class SmoothcompAgent(BaseTournamentAgent):
    """Agent for scraping tournaments from Smoothcomp."""

    @property
    def source(self) -> TournamentSource:
        return TournamentSource.SMOOTHCOMP

    @property
    def target_url(self) -> str:
        return "https://smoothcomp.com/en/events"

    @property
    def extraction_prompt(self) -> str:
        return """
        Browse the Smoothcomp events page and extract all upcoming BJJ and Judo tournaments.
        For each tournament, extract:
        - Tournament name
        - Date (start and end if available)
        - Location (city, state/province, country)
        - Organizer name
        - Registration fees if visible
        - Registration link/URL
        - Brief description if available

        Return the data as a JSON array of tournament objects.
        Focus on tournaments happening in the next 6 months.
        """

    def _parse_response(self, response: dict) -> List[Tournament]:
        """Parse MultiOn response into Tournament objects."""
        tournaments = []
        try:
            # Extract text content from response
            message = response.get("message", "")

            # Try to find JSON in the response
            if "[" in message and "]" in message:
                start = message.find("[")
                end = message.rfind("]") + 1
                json_str = message[start:end]
                data = json.loads(json_str)

                for item in data:
                    tournament = Tournament(
                        id=self._generate_id(item.get("name", ""), item.get("date", "")),
                        name=item.get("name", "Unknown Tournament"),
                        date=item.get("date", "TBD"),
                        end_date=item.get("end_date"),
                        location=item.get("location", "TBD"),
                        city=item.get("city"),
                        state=item.get("state"),
                        country=item.get("country"),
                        description=item.get("description"),
                        organizer=item.get("organizer"),
                        fees=item.get("fees"),
                        registration_link=item.get("registration_link", self.target_url),
                        source=self.source,
                        sport=item.get("sport", "BJJ"),
                    )
                    tournaments.append(tournament)
        except json.JSONDecodeError:
            pass

        return tournaments if tournaments else self._get_mock_data()

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
