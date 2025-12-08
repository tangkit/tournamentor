import os
import json
import re
from typing import List, Tuple, Optional
from openai import AsyncOpenAI

from ..models import Tournament, ChatMessage, TournamentSource


# Common country names and their variations
COUNTRY_ALIASES = {
    # North America
    "usa": "USA", "us": "USA", "united states": "USA", "america": "USA", "u.s.": "USA", "u.s.a.": "USA",
    "canada": "Canada", "ca": "Canada",
    "mexico": "Mexico",
    # Europe
    "uk": "UK", "united kingdom": "UK", "england": "UK", "britain": "UK", "great britain": "UK",
    "ireland": "Ireland",
    "portugal": "Portugal",
    "spain": "Spain",
    "france": "France",
    "germany": "Germany",
    "italy": "Italy",
    "netherlands": "Netherlands", "holland": "Netherlands",
    "belgium": "Belgium",
    "sweden": "Sweden",
    "norway": "Norway",
    "denmark": "Denmark",
    "finland": "Finland",
    "poland": "Poland",
    "austria": "Austria",
    "switzerland": "Switzerland",
    # Asia
    "japan": "Japan",
    "south korea": "South Korea", "korea": "South Korea",
    "china": "China",
    "hong kong": "China",
    "taiwan": "Taiwan",
    "singapore": "Singapore",
    "thailand": "Thailand",
    "philippines": "Philippines",
    "malaysia": "Malaysia",
    "indonesia": "Indonesia",
    "vietnam": "Vietnam",
    "india": "India",
    "uae": "UAE", "united arab emirates": "UAE", "dubai": "UAE",
    # Oceania
    "australia": "Australia", "aus": "Australia",
    "new zealand": "New Zealand", "nz": "New Zealand",
    # South America
    "brazil": "Brazil",
    "argentina": "Argentina",
    "chile": "Chile",
    "colombia": "Colombia",
    "peru": "Peru",
}

# Region to countries mapping
REGION_COUNTRIES = {
    "asia": ["Japan", "South Korea", "China", "Singapore", "Thailand", "Philippines", "Malaysia", "Indonesia", "Vietnam", "India", "UAE", "Taiwan"],
    "europe": ["UK", "Ireland", "Portugal", "Spain", "France", "Germany", "Italy", "Netherlands", "Belgium", "Sweden", "Norway", "Denmark", "Finland", "Poland", "Austria", "Switzerland"],
    "north america": ["USA", "Canada", "Mexico"],
    "south america": ["Brazil", "Argentina", "Chile", "Colombia", "Peru"],
    "oceania": ["Australia", "New Zealand"],
    "americas": ["USA", "Canada", "Mexico", "Brazil", "Argentina", "Chile", "Colombia", "Peru"],
    "pacific": ["Australia", "New Zealand", "Japan", "Philippines", "Indonesia"],
    "southeast asia": ["Singapore", "Thailand", "Philippines", "Malaysia", "Indonesia", "Vietnam"],
    "east asia": ["Japan", "South Korea", "China", "Taiwan"],
    "middle east": ["UAE"],
    "scandinavia": ["Sweden", "Norway", "Denmark", "Finland"],
}


class ChatService:
    """Service for handling chat interactions and coordinating tournament searches."""

    def __init__(self):
        self.client = AsyncOpenAI(api_key=os.getenv("OPENAI_API_KEY", "demo"))

    async def process_message(
        self,
        message: str,
        history: List[ChatMessage],
        tournaments: List[Tournament] = []
    ) -> Tuple[str, bool]:
        """
        Process a user message and determine if a tournament search is needed.

        Returns:
            Tuple of (response_message, should_search)
        """
        system_prompt = """You are Tournamentor, a helpful AI assistant specialized in finding BJJ (Brazilian Jiu-Jitsu) and Judo tournaments.

Your capabilities:
- Search for tournaments from multiple sources: Smoothcomp, IBJJF, ASJJF, NAGA, and Grappling Industries
- Filter by location (country, region, city, state), date range, and tournament type
- Provide information about registration fees, deadlines, and event details

When a user asks about tournaments:
1. Extract any location preferences - this can be:
   - Specific countries (e.g., "USA", "Japan", "Brazil")
   - Multiple countries (e.g., "USA and Canada", "Japan, Korea, and Singapore")
   - Regions (e.g., "Asia", "Europe", "North America", "Southeast Asia")
   - Cities or states (e.g., "California", "Tokyo")
2. Extract any date preferences
3. Extract any specific organization preferences (IBJJF, NAGA, etc.)
4. If the query is about finding tournaments, respond with SEARCH_TOURNAMENTS at the start of your response

Example responses:
- User: "Find BJJ tournaments in California"
  Response: "SEARCH_TOURNAMENTS
  I'll search for BJJ tournaments in California for you!"

- User: "Show me tournaments in Asia"
  Response: "SEARCH_TOURNAMENTS
  I'll search for tournaments across Asia (Japan, Korea, Singapore, Thailand, etc.) for you!"

- User: "Find competitions in USA and Canada"
  Response: "SEARCH_TOURNAMENTS
  I'll search for tournaments in USA and Canada for you!"

- User: "What IBJJF events are in Europe?"
  Response: "SEARCH_TOURNAMENTS
  Let me find IBJJF events across Europe for you!"

- User: "Hello!"
  Response: "Hello! I'm Tournamentor, your AI assistant for finding BJJ and Judo tournaments worldwide. I can help you find competitions by:
  - Country (USA, Japan, Brazil, etc.)
  - Region (Asia, Europe, North America, etc.)
  - Organization (IBJJF, NAGA, Smoothcomp, etc.)
  Just tell me what you're looking for!"

If the user is just chatting or asking questions about the tournaments already shown, respond naturally without the SEARCH_TOURNAMENTS prefix.

Always be helpful, friendly, and knowledgeable about the BJJ/Judo competition scene."""

        messages = [{"role": "system", "content": system_prompt}]

        # Add tournament context if available
        if tournaments:
            tournament_summary = self._summarize_tournaments(tournaments)
            messages.append({
                "role": "system",
                "content": f"Current tournaments shown to user:\n{tournament_summary}"
            })

        # Add conversation history
        for msg in history[-10:]:  # Keep last 10 messages for context
            messages.append({"role": msg.role, "content": msg.content})

        messages.append({"role": "user", "content": message})

        try:
            response = await self.client.chat.completions.create(
                model="gpt-4o-mini",
                messages=messages,
                temperature=0.7,
                max_tokens=500
            )

            response_text = response.choices[0].message.content
            should_search = response_text.startswith("SEARCH_TOURNAMENTS")

            # Clean up the response for display
            if should_search:
                # Extract the search parameters and clean response
                lines = response_text.split("\n", 1)
                if len(lines) > 1:
                    response_text = lines[1].strip()
                else:
                    response_text = "Let me search for tournaments for you!"

            return response_text, should_search

        except Exception as e:
            print(f"Chat service error: {e}")
            # Fallback response
            if any(word in message.lower() for word in ["find", "search", "tournament", "competition", "event"]):
                return "I'll search for tournaments for you!", True
            return "I'm here to help you find BJJ and Judo tournaments. What are you looking for?", False

    def parse_search_intent(self, message: str) -> dict:
        """Parse user message to extract search parameters including geography."""
        params = {
            "location": None,
            "countries": [],
            "sources": [],
            "date_from": None,
            "date_to": None
        }

        message_lower = message.lower()

        # Extract countries from message
        countries = self._extract_countries(message_lower)
        if countries:
            params["countries"] = countries

        # Extract regions and expand to countries
        regions = self._extract_regions(message_lower)
        for region in regions:
            region_countries = REGION_COUNTRIES.get(region, [])
            for country in region_countries:
                if country not in params["countries"]:
                    params["countries"].append(country)

        # If no countries found, try to extract general location
        if not params["countries"]:
            location_patterns = [
                r"in\s+([A-Za-z\s,]+?)(?:\s+(?:from|between|this|next|and\s+|$))",
                r"near\s+([A-Za-z\s]+?)(?:\s+(?:from|between|this|next|$))",
                r"around\s+([A-Za-z\s]+?)(?:\s+(?:from|between|this|next|$))",
            ]
            for pattern in location_patterns:
                match = re.search(pattern, message, re.IGNORECASE)
                if match:
                    location = match.group(1).strip().rstrip(',')
                    # Check if it's a known country
                    normalized = COUNTRY_ALIASES.get(location.lower())
                    if normalized:
                        params["countries"].append(normalized)
                    else:
                        params["location"] = location
                    break

        # Extract sources
        source_keywords = {
            "ibjjf": TournamentSource.IBJJF,
            "smoothcomp": TournamentSource.SMOOTHCOMP,
            "asjjf": TournamentSource.ASJJF,
            "naga": TournamentSource.NAGA,
            "grappling industries": TournamentSource.GRAPPLING_INDUSTRIES,
        }

        for keyword, source in source_keywords.items():
            if keyword in message_lower:
                params["sources"].append(source)

        return params

    def _extract_countries(self, message: str) -> List[str]:
        """Extract country names from message."""
        countries = []
        message_lower = message.lower()

        # Sort by length (longest first) to match multi-word countries first
        sorted_aliases = sorted(COUNTRY_ALIASES.keys(), key=len, reverse=True)

        for alias in sorted_aliases:
            # Use word boundary matching
            pattern = r'\b' + re.escape(alias) + r'\b'
            if re.search(pattern, message_lower):
                country = COUNTRY_ALIASES[alias]
                if country not in countries:
                    countries.append(country)

        return countries

    def _extract_regions(self, message: str) -> List[str]:
        """Extract region names from message."""
        regions = []
        message_lower = message.lower()

        for region in REGION_COUNTRIES.keys():
            pattern = r'\b' + re.escape(region) + r'\b'
            if re.search(pattern, message_lower):
                regions.append(region)

        return regions

    def _summarize_tournaments(self, tournaments: List[Tournament]) -> str:
        """Create a brief summary of tournaments for context."""
        if not tournaments:
            return "No tournaments currently displayed."

        summary_lines = []
        for t in tournaments[:10]:  # Limit to 10 for context
            summary_lines.append(
                f"- {t.name} on {t.date} in {t.location} ({t.source.value})"
            )

        return "\n".join(summary_lines)
