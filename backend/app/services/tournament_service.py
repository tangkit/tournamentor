import asyncio
from typing import List, Optional
from datetime import datetime

from ..models import Tournament, TournamentSource
from ..agents.smoothcomp_agent import SmoothcompAgent
from ..agents.ibjjf_agent import IBJJFAgent
from ..agents.asjjf_agent import ASJJFAgent
from ..agents.naga_agent import NAGAAgent
from ..agents.grappling_industries_agent import GrapplingIndustriesAgent


class TournamentService:
    """Service for aggregating tournaments from multiple sources."""

    def __init__(self):
        self.agents = {
            TournamentSource.SMOOTHCOMP: SmoothcompAgent(),
            TournamentSource.IBJJF: IBJJFAgent(),
            TournamentSource.ASJJF: ASJJFAgent(),
            TournamentSource.NAGA: NAGAAgent(),
            TournamentSource.GRAPPLING_INDUSTRIES: GrapplingIndustriesAgent(),
        }

    async def search_tournaments(
        self,
        sources: List[TournamentSource] = None,
        location: Optional[str] = None,
        date_from: Optional[str] = None,
        date_to: Optional[str] = None,
    ) -> List[Tournament]:
        """
        Search for tournaments across multiple sources.

        Args:
            sources: List of sources to search (None = all sources)
            location: Location filter (city, state, or country)
            date_from: Start date filter (YYYY-MM-DD)
            date_to: End date filter (YYYY-MM-DD)

        Returns:
            List of Tournament objects sorted by date
        """
        if not sources:
            sources = list(self.agents.keys())

        # Run all agent scrapes concurrently
        tasks = []
        for source in sources:
            if source in self.agents:
                agent = self.agents[source]
                tasks.append(agent.scrape_tournaments(location))

        results = await asyncio.gather(*tasks, return_exceptions=True)

        # Combine all tournaments
        all_tournaments = []
        for result in results:
            if isinstance(result, list):
                all_tournaments.extend(result)
            elif isinstance(result, Exception):
                print(f"Agent error: {result}")

        # Apply filters
        filtered = self._apply_filters(
            all_tournaments,
            location=location,
            date_from=date_from,
            date_to=date_to
        )

        # Sort by date
        filtered.sort(key=lambda t: t.date if t.date != "TBD" else "9999-99-99")

        return filtered

    def _apply_filters(
        self,
        tournaments: List[Tournament],
        location: Optional[str] = None,
        date_from: Optional[str] = None,
        date_to: Optional[str] = None,
    ) -> List[Tournament]:
        """Apply location and date filters to tournament list."""
        filtered = tournaments

        if location:
            location_lower = location.lower()
            filtered = [
                t for t in filtered
                if location_lower in t.location.lower()
                or (t.city and location_lower in t.city.lower())
                or (t.state and location_lower in t.state.lower())
                or (t.country and location_lower in t.country.lower())
            ]

        if date_from:
            filtered = [
                t for t in filtered
                if t.date >= date_from or t.date == "TBD"
            ]

        if date_to:
            filtered = [
                t for t in filtered
                if t.date <= date_to or t.date == "TBD"
            ]

        return filtered

    async def get_all_tournaments(self) -> List[Tournament]:
        """Get all tournaments from all sources."""
        return await self.search_tournaments()

    async def get_tournaments_by_source(self, source: TournamentSource) -> List[Tournament]:
        """Get tournaments from a specific source."""
        return await self.search_tournaments(sources=[source])
