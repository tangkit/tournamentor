import asyncio
from typing import List, Optional
from datetime import datetime

from ..models import Tournament, TournamentSource
from ..agents.smoothcomp_agent import SmoothcompAgent
from ..agents.ibjjf_agent import IBJJFAgent
from ..agents.asjjf_agent import ASJJFAgent
from ..agents.naga_agent import NAGAAgent


class TournamentService:
    """Service for aggregating tournaments from multiple sources."""

    def __init__(self):
        self.agents = {
            TournamentSource.SMOOTHCOMP: SmoothcompAgent(),
            TournamentSource.IBJJF: IBJJFAgent(),
            TournamentSource.ASJJF: ASJJFAgent(),
            TournamentSource.NAGA: NAGAAgent(),
        }

    async def search_tournaments(
        self,
        sources: List[TournamentSource] = None,
        location: Optional[str] = None,
        countries: Optional[List[str]] = None,
        date_from: Optional[str] = None,
        date_to: Optional[str] = None,
    ) -> List[Tournament]:
        """
        Search for tournaments across multiple sources.

        Args:
            sources: List of sources to search (None = all sources)
            location: Location filter (city, state, or country)
            countries: List of countries to filter by
            date_from: Start date filter (YYYY-MM-DD)
            date_to: End date filter (YYYY-MM-DD)

        Returns:
            List of Tournament objects sorted by date
        """
        if not sources:
            sources = list(self.agents.keys())

        # If location is not set but countries are specified, pass all countries
        # as a comma-separated string so agents can filter by multiple countries
        effective_location = location
        if not effective_location and countries:
            effective_location = ",".join(countries)
            print(f"[TournamentService] Using countries '{effective_location}' as location filter for agents")

        # Run agents sequentially (Notte free plan allows only 1 concurrent session)
        all_tournaments = []
        for source in sources:
            if source in self.agents:
                agent = self.agents[source]
                print(f"[TournamentService] Starting scrape for {source.value}...")
                try:
                    result = await agent.scrape_tournaments(effective_location)
                    if isinstance(result, list):
                        print(f"[TournamentService] {source.value}: Found {len(result)} tournaments")
                        all_tournaments.extend(result)
                    else:
                        print(f"[TournamentService] {source.value}: No tournaments returned")
                except Exception as e:
                    print(f"[TournamentService] {source.value} error: {e}")
                    import traceback
                    traceback.print_exc()

        # Apply filters
        filtered = self._apply_filters(
            all_tournaments,
            location=location,
            countries=countries,
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
        countries: Optional[List[str]] = None,
        date_from: Optional[str] = None,
        date_to: Optional[str] = None,
    ) -> List[Tournament]:
        """Apply location, country, and date filters to tournament list."""
        filtered = tournaments

        # Filter by countries if specified
        if countries:
            countries_lower = [c.lower() for c in countries]
            filtered = [
                t for t in filtered
                if self._matches_country(t, countries_lower)
            ]

        # Filter by location if specified (more specific than country)
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

    def _matches_country(self, tournament: Tournament, countries_lower: List[str]) -> bool:
        """Check if tournament matches any of the specified countries."""
        # Check tournament country field
        if tournament.country:
            tournament_country = tournament.country.lower()
            for country in countries_lower:
                if country in tournament_country or tournament_country in country:
                    return True

        # Check location string for country matches
        if tournament.location:
            location_lower = tournament.location.lower()
            for country in countries_lower:
                if country in location_lower:
                    return True

        return False

    async def get_all_tournaments(self) -> List[Tournament]:
        """Get all tournaments from all sources."""
        return await self.search_tournaments()

    async def get_tournaments_by_source(self, source: TournamentSource) -> List[Tournament]:
        """Get tournaments from a specific source."""
        return await self.search_tournaments(sources=[source])
