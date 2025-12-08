import os
import json
import re
from typing import List, Tuple, Optional
from openai import AsyncOpenAI

from ..models import Tournament, ChatMessage, TournamentSource


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
- Filter by location, date range, and tournament type
- Provide information about registration fees, deadlines, and event details

When a user asks about tournaments:
1. Extract any location preferences (city, state, country)
2. Extract any date preferences
3. Extract any specific organization preferences (IBJJF, NAGA, etc.)
4. If the query is about finding tournaments, respond with SEARCH_TOURNAMENTS at the start of your response, followed by a JSON object with the search parameters

Example responses:
- User: "Find BJJ tournaments in California"
  Response: "SEARCH_TOURNAMENTS {"location": "California", "sources": ["all"]}
  I'll search for BJJ tournaments in California for you!"

- User: "What IBJJF events are coming up?"
  Response: "SEARCH_TOURNAMENTS {"sources": ["ibjjf"]}
  Let me find upcoming IBJJF events for you!"

- User: "Hello!"
  Response: "Hello! I'm Tournamentor, your AI assistant for finding BJJ and Judo tournaments. I can help you find upcoming competitions from Smoothcomp, IBJJF, ASJJF, NAGA, and Grappling Industries. Just tell me what you're looking for - whether it's tournaments in a specific location, from a particular organization, or within a certain date range!"

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
        """Parse user message to extract search parameters."""
        params = {
            "location": None,
            "sources": [],
            "date_from": None,
            "date_to": None
        }

        message_lower = message.lower()

        # Extract location
        location_patterns = [
            r"in\s+([A-Za-z\s]+?)(?:\s+(?:from|between|this|next|$))",
            r"near\s+([A-Za-z\s]+?)(?:\s+(?:from|between|this|next|$))",
            r"around\s+([A-Za-z\s]+?)(?:\s+(?:from|between|this|next|$))",
        ]
        for pattern in location_patterns:
            match = re.search(pattern, message, re.IGNORECASE)
            if match:
                params["location"] = match.group(1).strip()
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
