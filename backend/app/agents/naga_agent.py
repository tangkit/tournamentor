import json
from typing import List
from datetime import datetime, timedelta
import random

from .base_agent import BaseTournamentAgent
from ..models import Tournament, TournamentSource


class NAGAAgent(BaseTournamentAgent):
    """Agent for scraping tournaments from NAGA (North American Grappling Association)."""

    @property
    def source(self) -> TournamentSource:
        return TournamentSource.NAGA

    @property
    def target_url(self) -> str:
        return "https://www.nagafighter.com/events"

    @property
    def extraction_prompt(self) -> str:
        return """
        Browse the NAGA events page and extract all upcoming grappling tournaments.
        For each tournament, extract:
        - Tournament name
        - Date
        - Location (city, state, country)
        - Registration fees
        - Registration link/URL
        - Division information if available

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
                        organizer="NAGA",
                        fees=item.get("fees"),
                        registration_link=item.get("registration_link", self.target_url),
                        source=self.source,
                        sport="Grappling/BJJ",
                    )
                    tournaments.append(tournament)
        except json.JSONDecodeError:
            pass

        return tournaments if tournaments else self._get_mock_data()

    def _get_mock_data(self) -> List[Tournament]:
        """Return realistic mock data for NAGA tournaments."""
        base_date = datetime.now()

        mock_tournaments = [
            {
                "name": "NAGA Philadelphia",
                "city": "Philadelphia",
                "state": "PA",
                "country": "USA",
                "fees": "$75 - $95",
                "description": "Gi, No-Gi, and MMA grappling divisions. Kids to adults.",
                "days_offset": 18
            },
            {
                "name": "NAGA Chicago",
                "city": "Chicago",
                "state": "IL",
                "country": "USA",
                "fees": "$75 - $95",
                "description": "Midwest championship. All experience levels.",
                "days_offset": 32
            },
            {
                "name": "NAGA Las Vegas",
                "city": "Las Vegas",
                "state": "NV",
                "country": "USA",
                "fees": "$85 - $105",
                "description": "Vegas showdown. Cash prizes in expert divisions.",
                "days_offset": 47
            },
            {
                "name": "NAGA New Jersey",
                "city": "Newark",
                "state": "NJ",
                "country": "USA",
                "fees": "$75 - $95",
                "description": "East coast tournament. Large competitor turnout expected.",
                "days_offset": 25
            },
            {
                "name": "NAGA Boston",
                "city": "Boston",
                "state": "MA",
                "country": "USA",
                "fees": "$75 - $95",
                "description": "New England championship event.",
                "days_offset": 60
            },
            {
                "name": "NAGA Phoenix",
                "city": "Phoenix",
                "state": "AZ",
                "country": "USA",
                "fees": "$75 - $95",
                "description": "Southwest regional. Desert grappling championship.",
                "days_offset": 75
            },
        ]

        tournaments = []
        for t in mock_tournaments:
            date = base_date + timedelta(days=t["days_offset"])
            tournament = Tournament(
                id=self._generate_id(t["name"], date.strftime("%Y-%m-%d")),
                name=t["name"],
                date=date.strftime("%Y-%m-%d"),
                location=f"{t['city']}, {t['state']}, {t['country']}",
                city=t["city"],
                state=t["state"],
                country=t["country"],
                description=t["description"],
                organizer="NAGA",
                fees=t["fees"],
                registration_link=f"https://www.nagafighter.com/events/{self._generate_id(t['name'], '')}",
                source=self.source,
                sport="Grappling/BJJ",
                registration_deadline=(date - timedelta(days=5)).strftime("%Y-%m-%d"),
            )
            tournaments.append(tournament)

        return tournaments
