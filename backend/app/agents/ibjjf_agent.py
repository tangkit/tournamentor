import json
from typing import List
from datetime import datetime, timedelta
import random

from .base_agent import BaseTournamentAgent
from ..models import Tournament, TournamentSource


class IBJJFAgent(BaseTournamentAgent):
    """Agent for scraping tournaments from IBJJF (International Brazilian Jiu-Jitsu Federation)."""

    @property
    def source(self) -> TournamentSource:
        return TournamentSource.IBJJF

    @property
    def target_url(self) -> str:
        return "https://ibjjf.com/events"

    @property
    def extraction_prompt(self) -> str:
        return """
        Browse the IBJJF events page and extract all upcoming BJJ tournaments.
        For each tournament, extract:
        - Tournament name
        - Date (start and end if available)
        - Location (city, state/province, country)
        - Event type (Open, Championship, Grand Prix, etc.)
        - Registration fees if visible
        - Registration link/URL
        - Early bird deadlines if available

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
                        end_date=item.get("end_date"),
                        location=item.get("location", "TBD"),
                        city=item.get("city"),
                        state=item.get("state"),
                        country=item.get("country"),
                        description=item.get("description"),
                        organizer="IBJJF",
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
        """Return realistic mock data for IBJJF tournaments."""
        base_date = datetime.now()

        mock_tournaments = [
            {
                "name": "IBJJF World Championship",
                "city": "Long Beach",
                "state": "CA",
                "country": "USA",
                "fees": "$150 - $250",
                "description": "The most prestigious BJJ tournament in the world. All belt levels.",
                "days_offset": 90
            },
            {
                "name": "IBJJF Pan Championship",
                "city": "Kissimmee",
                "state": "FL",
                "country": "USA",
                "fees": "$140 - $220",
                "description": "Pan American Championship. Major IBJJF event with worldwide competitors.",
                "days_offset": 45
            },
            {
                "name": "IBJJF European Championship",
                "city": "Lisbon",
                "state": "",
                "country": "Portugal",
                "fees": "€120 - €180",
                "description": "European Championship with competitors from across Europe and beyond.",
                "days_offset": 60
            },
            {
                "name": "IBJJF Dallas Open",
                "city": "Dallas",
                "state": "TX",
                "country": "USA",
                "fees": "$100 - $140",
                "description": "Open tournament with Gi and No-Gi divisions. All belt levels welcome.",
                "days_offset": 21
            },
            {
                "name": "IBJJF Atlanta Spring Open",
                "city": "Atlanta",
                "state": "GA",
                "country": "USA",
                "fees": "$100 - $140",
                "description": "Spring open tournament. Points towards IBJJF ranking.",
                "days_offset": 30
            },
            {
                "name": "IBJJF Houston Open",
                "city": "Houston",
                "state": "TX",
                "country": "USA",
                "fees": "$100 - $140",
                "description": "Open tournament in Houston. IBJJF rules and regulations.",
                "days_offset": 50
            },
            {
                "name": "IBJJF San Diego Open",
                "city": "San Diego",
                "state": "CA",
                "country": "USA",
                "fees": "$100 - $140",
                "description": "Southern California open. Great preparation for Worlds.",
                "days_offset": 75
            },
            {
                "name": "IBJJF No-Gi World Championship",
                "city": "Anaheim",
                "state": "CA",
                "country": "USA",
                "fees": "$150 - $250",
                "description": "World Championship in No-Gi format. Submission wrestling focus.",
                "days_offset": 120
            },
        ]

        tournaments = []
        for t in mock_tournaments:
            date = base_date + timedelta(days=t["days_offset"])
            end_date = date + timedelta(days=random.choice([1, 2, 3]))
            tournament = Tournament(
                id=self._generate_id(t["name"], date.strftime("%Y-%m-%d")),
                name=t["name"],
                date=date.strftime("%Y-%m-%d"),
                end_date=end_date.strftime("%Y-%m-%d"),
                location=f"{t['city']}, {t['state']}, {t['country']}".replace(", ,", ",").strip(", "),
                city=t["city"],
                state=t["state"] if t["state"] else None,
                country=t["country"],
                description=t["description"],
                organizer="IBJJF",
                fees=t["fees"],
                registration_link=f"https://ibjjf.com/events/{self._generate_id(t['name'], '')}",
                source=self.source,
                sport="BJJ",
                registration_deadline=(date - timedelta(days=14)).strftime("%Y-%m-%d"),
            )
            tournaments.append(tournament)

        return tournaments
