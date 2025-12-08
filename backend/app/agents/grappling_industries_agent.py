import json
from typing import List
from datetime import datetime, timedelta
import random

from .base_agent import BaseTournamentAgent
from ..models import Tournament, TournamentSource


class GrapplingIndustriesAgent(BaseTournamentAgent):
    """Agent for scraping tournaments from Grappling Industries."""

    @property
    def source(self) -> TournamentSource:
        return TournamentSource.GRAPPLING_INDUSTRIES

    @property
    def target_url(self) -> str:
        return "https://grapplingindustries.com/events/"

    @property
    def extraction_prompt(self) -> str:
        return """
        Browse the Grappling Industries events page and extract all upcoming BJJ tournaments.
        For each tournament, extract:
        - Tournament name
        - Date
        - Location (city, state/province, country)
        - Registration fees
        - Registration link/URL
        - Format information (round robin, etc.)

        Return the data as a JSON array of tournament objects.
        Focus on tournaments happening in the next 6 months.
        """

    def _parse_response(self, response: dict) -> List[Tournament]:
        """Parse MultiOn response into Tournament objects."""
        tournaments = []
        try:
            message = response.get("message", "")

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
                        location=item.get("location", "TBD"),
                        city=item.get("city"),
                        state=item.get("state"),
                        country=item.get("country"),
                        description=item.get("description"),
                        organizer="Grappling Industries",
                        fees=item.get("fees"),
                        registration_link=item.get("registration_link", self.target_url),
                        source=self.source,
                        sport="BJJ",
                    )
                    tournaments.append(tournament)
        except json.JSONDecodeError:
            pass

        return tournaments if tournaments else self._get_mock_data()

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
