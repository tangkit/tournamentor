import os
from typing import List, Optional
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from dotenv import load_dotenv

from .models import (
    Tournament,
    TournamentSource,
    ChatRequest,
    ChatResponse,
    SearchRequest,
    SearchResponse,
)
from .services.tournament_service import TournamentService
from .services.chat_service import ChatService

# Load environment variables
load_dotenv()

app = FastAPI(
    title="Tournamentor API",
    description="AI-powered BJJ and Judo tournament aggregator",
    version="1.0.0"
)

# Configure CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # In production, specify actual origins
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Initialize services
tournament_service = TournamentService()
chat_service = ChatService()

# Store for current session tournaments
current_tournaments: List[Tournament] = []


@app.get("/")
async def root():
    """Root endpoint with API info."""
    return {
        "name": "Tournamentor API",
        "version": "1.0.0",
        "description": "AI-powered BJJ and Judo tournament aggregator",
        "endpoints": {
            "chat": "/api/chat",
            "search": "/api/tournaments/search",
            "all_tournaments": "/api/tournaments",
            "sources": "/api/sources"
        }
    }


@app.post("/api/chat", response_model=ChatResponse)
async def chat(request: ChatRequest):
    """
    Chat endpoint for conversational tournament search.

    Send a message and receive AI-powered responses with relevant tournaments.
    """
    global current_tournaments

    try:
        # Process the message through chat service
        response_text, should_search = await chat_service.process_message(
            request.message,
            request.history,
            current_tournaments
        )

        tournaments = []

        if should_search:
            # Parse search intent from user message
            search_params = chat_service.parse_search_intent(request.message)

            # Search for tournaments
            tournaments = await tournament_service.search_tournaments(
                sources=search_params.get("sources") or None,
                location=search_params.get("location"),
                date_from=search_params.get("date_from"),
                date_to=search_params.get("date_to"),
            )

            current_tournaments = tournaments

            # Update response with result count
            if tournaments:
                response_text = f"{response_text}\n\nI found {len(tournaments)} tournaments for you!"
            else:
                response_text = f"{response_text}\n\nI couldn't find any tournaments matching your criteria. Try broadening your search!"

        return ChatResponse(
            message=response_text,
            tournaments=tournaments
        )

    except Exception as e:
        print(f"Chat error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/tournaments/search", response_model=SearchResponse)
async def search_tournaments(request: SearchRequest):
    """
    Search for tournaments with specific filters.

    - **query**: Optional text search query
    - **sources**: List of sources to search (empty = all)
    - **location**: Location filter (city, state, or country)
    - **date_from**: Start date filter (YYYY-MM-DD)
    - **date_to**: End date filter (YYYY-MM-DD)
    """
    try:
        tournaments = await tournament_service.search_tournaments(
            sources=request.sources if request.sources else None,
            location=request.location,
            date_from=request.date_from,
            date_to=request.date_to,
        )

        message = f"Found {len(tournaments)} tournaments"
        if request.location:
            message += f" in {request.location}"
        if request.sources:
            sources_str = ", ".join(s.value for s in request.sources)
            message += f" from {sources_str}"

        return SearchResponse(
            tournaments=tournaments,
            message=message
        )

    except Exception as e:
        print(f"Search error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/tournaments", response_model=List[Tournament])
async def get_all_tournaments():
    """Get all tournaments from all sources."""
    try:
        return await tournament_service.get_all_tournaments()
    except Exception as e:
        print(f"Get tournaments error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/tournaments/{source}", response_model=List[Tournament])
async def get_tournaments_by_source(source: TournamentSource):
    """Get tournaments from a specific source."""
    try:
        return await tournament_service.get_tournaments_by_source(source)
    except Exception as e:
        print(f"Get tournaments by source error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/sources")
async def get_sources():
    """Get list of available tournament sources."""
    return {
        "sources": [
            {"id": "smoothcomp", "name": "Smoothcomp", "url": "https://smoothcomp.com"},
            {"id": "ibjjf", "name": "IBJJF", "url": "https://ibjjf.com"},
            {"id": "asjjf", "name": "ASJJF", "url": "https://www.asjjf.org"},
            {"id": "naga", "name": "NAGA", "url": "https://www.nagafighter.com"},
            {"id": "grappling_industries", "name": "Grappling Industries", "url": "https://grapplingindustries.com"},
        ]
    }


@app.get("/health")
async def health_check():
    """Health check endpoint."""
    return {"status": "healthy"}
