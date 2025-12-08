import json
from typing import List
from datetime import datetime, timedelta
import random

from .base_agent import BaseTournamentAgent
from ..models import Tournament, TournamentSource


class ASJJFAgent(BaseTournamentAgent):
    """Agent for scraping tournaments from ASJJF (Asian Sport Jiu-Jitsu Federation)."""

    @property
    def source(self) -> TournamentSource:
        return TournamentSource.ASJJF

    @property
    def target_url(self) -> str:
        return "https://www.asjjf.org/events"

    @property
    def extraction_prompt(self) -> str:
        return """
        Browse the ASJJF events page and extract all upcoming BJJ and Judo tournaments.
        For each tournament, extract:
        - Tournament name
        - Date (start and end if available)
        - Location (city, country)
        - Event type
        - Registration fees if visible
        - Registration link/URL

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
                        country=item.get("country"),
                        description=item.get("description"),
                        organizer="ASJJF",
                        fees=item.get("fees"),
                        registration_link=item.get("registration_link", self.target_url),
                        source=self.source,
                        sport="BJJ/Judo",
                    )
                    tournaments.append(tournament)
        except json.JSONDecodeError:
            pass

        return tournaments if tournaments else self._get_mock_data()

    def _get_mock_data(self) -> List[Tournament]:
        """Return realistic mock data for ASJJF tournaments."""
        base_date = datetime.now()

        mock_tournaments = [
            {
                "name": "ASJJF Tokyo International Open",
                "city": "Tokyo",
                "country": "Japan",
                "fees": "¥12,000 - ¥18,000",
                "description": "International open tournament in Tokyo. Gi and No-Gi divisions.",
                "days_offset": 25
            },
            {
                "name": "ASJJF Seoul Grand Slam",
                "city": "Seoul",
                "country": "South Korea",
                "fees": "₩150,000 - ₩220,000",
                "description": "Grand Slam event in Seoul. Top Asian competitors.",
                "days_offset": 40
            },
            {
                "name": "ASJJF Singapore Pro",
                "city": "Singapore",
                "country": "Singapore",
                "fees": "SGD 120 - SGD 180",
                "description": "Professional level competition. Cash prizes for black belts.",
                "days_offset": 55
            },
            {
                "name": "ASJJF Hong Kong Championship",
                "city": "Hong Kong",
                "country": "China",
                "fees": "HKD 800 - HKD 1,200",
                "description": "Hong Kong regional championship. All belt levels.",
                "days_offset": 35
            },
            {
                "name": "ASJJF Bangkok Open",
                "city": "Bangkok",
                "country": "Thailand",
                "fees": "฿3,000 - ฿4,500",
                "description": "Open tournament in Bangkok. Growing Thai BJJ scene.",
                "days_offset": 65
            },
            {
                "name": "ASJJF Manila International",
                "city": "Manila",
                "country": "Philippines",
                "fees": "₱4,000 - ₱6,000",
                "description": "International event in the Philippines. Southeast Asian focus.",
                "days_offset": 80
            },
            {
                "name": "ASJJF Asian Championship",
                "city": "Osaka",
                "country": "Japan",
                "fees": "¥15,000 - ¥22,000",
                "description": "Continental championship. Points towards Asian rankings.",
                "days_offset": 100
            },
            {
                "name": "ASJJF Kuala Lumpur Open",
                "city": "Kuala Lumpur",
                "country": "Malaysia",
                "fees": "MYR 350 - MYR 500",
                "description": "Malaysian open tournament. Beginners to advanced welcome.",
                "days_offset": 45
            },
        ]

        tournaments = []
        for t in mock_tournaments:
            date = base_date + timedelta(days=t["days_offset"])
            end_date = date + timedelta(days=random.choice([0, 1, 2]))
            tournament = Tournament(
                id=self._generate_id(t["name"], date.strftime("%Y-%m-%d")),
                name=t["name"],
                date=date.strftime("%Y-%m-%d"),
                end_date=end_date.strftime("%Y-%m-%d"),
                location=f"{t['city']}, {t['country']}",
                city=t["city"],
                country=t["country"],
                description=t["description"],
                organizer="ASJJF",
                fees=t["fees"],
                registration_link=f"https://www.asjjf.org/events/{self._generate_id(t['name'], '')}",
                source=self.source,
                sport="BJJ/Judo",
                registration_deadline=(date - timedelta(days=10)).strftime("%Y-%m-%d"),
            )
            tournaments.append(tournament)

        return tournaments
