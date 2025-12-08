from pydantic import BaseModel
from typing import Optional, List
from datetime import datetime
from enum import Enum


class TournamentSource(str, Enum):
    SMOOTHCOMP = "smoothcomp"
    ASJJF = "asjjf"
    IBJJF = "ibjjf"
    NAGA = "naga"
    GRAPPLING_INDUSTRIES = "grappling_industries"
    OTHER = "other"


class Tournament(BaseModel):
    id: str
    name: str
    date: str
    end_date: Optional[str] = None
    location: str
    city: Optional[str] = None
    state: Optional[str] = None
    country: Optional[str] = None
    description: Optional[str] = None
    organizer: Optional[str] = None
    fees: Optional[str] = None
    registration_link: str
    source: TournamentSource
    sport: str = "BJJ/Judo"
    registration_deadline: Optional[str] = None
    scraped_at: datetime = datetime.now()


class ChatMessage(BaseModel):
    role: str  # "user" or "assistant"
    content: str


class ChatRequest(BaseModel):
    message: str
    history: List[ChatMessage] = []


class ChatResponse(BaseModel):
    message: str
    tournaments: List[Tournament] = []


class SearchRequest(BaseModel):
    query: Optional[str] = None
    sources: List[TournamentSource] = []
    location: Optional[str] = None
    countries: List[str] = []
    date_from: Optional[str] = None
    date_to: Optional[str] = None


class SearchResponse(BaseModel):
    tournaments: List[Tournament]
    message: str
