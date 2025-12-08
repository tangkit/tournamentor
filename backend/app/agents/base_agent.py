import os
import json
import httpx
from abc import ABC, abstractmethod
from typing import List, Optional
from datetime import datetime

from ..models import Tournament, TournamentSource


class BaseTournamentAgent(ABC):
    """Base class for tournament scraping agents using MultiOn AgentQ."""

    def __init__(self):
        self.multion_api_key = os.getenv("MULTION_API_KEY")
        self.base_url = "https://api.multion.ai/v1"

    @property
    @abstractmethod
    def source(self) -> TournamentSource:
        """The source this agent scrapes from."""
        pass

    @property
    @abstractmethod
    def target_url(self) -> str:
        """The URL to scrape tournaments from."""
        pass

    @property
    @abstractmethod
    def extraction_prompt(self) -> str:
        """The prompt for extracting tournament data."""
        pass

    async def scrape_tournaments(self, location: Optional[str] = None) -> List[Tournament]:
        """
        Use MultiOn AgentQ to browse and extract tournament data.
        """
        if not self.multion_api_key:
            # Return mock data if no API key is configured
            return self._get_mock_data()

        try:
            async with httpx.AsyncClient(timeout=120.0) as client:
                # Create a browsing session with MultiOn
                browse_payload = {
                    "cmd": self.extraction_prompt,
                    "url": self.target_url,
                    "local": False,
                    "include_screenshot": False
                }

                if location:
                    browse_payload["cmd"] += f" Focus on tournaments in or near {location}."

                response = await client.post(
                    f"{self.base_url}/browse",
                    headers={
                        "X-MULTION-API-KEY": self.multion_api_key,
                        "Content-Type": "application/json"
                    },
                    json=browse_payload
                )

                if response.status_code == 200:
                    result = response.json()
                    return self._parse_response(result)
                else:
                    print(f"MultiOn API error: {response.status_code} - {response.text}")
                    return self._get_mock_data()

        except Exception as e:
            print(f"Error scraping {self.source}: {e}")
            return self._get_mock_data()

    @abstractmethod
    def _parse_response(self, response: dict) -> List[Tournament]:
        """Parse the MultiOn response into Tournament objects."""
        pass

    @abstractmethod
    def _get_mock_data(self) -> List[Tournament]:
        """Return mock data for development/demo purposes."""
        pass

    def _generate_id(self, name: str, date: str) -> str:
        """Generate a unique ID for a tournament."""
        import hashlib
        return hashlib.md5(f"{self.source}:{name}:{date}".encode()).hexdigest()[:12]
