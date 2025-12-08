# Tournamentor

AI-powered BJJ and Judo tournament aggregator with a chat-style interface.

## Features

- **Chat-Style AI Interface**: Conversational search for tournaments
- **Multi-Source Aggregation**: Pulls tournaments from:
  - Smoothcomp
  - IBJJF (International Brazilian Jiu-Jitsu Federation)
  - ASJJF (Asian Sport Jiu-Jitsu Federation)
  - NAGA (North American Grappling Association)
  - Grappling Industries
- **Smart Filtering**: Filter by location, date, source, and more
- **Sortable Table**: Sort tournaments by any column
- **Excel Export**: Export tournament data to Excel spreadsheet
- **Responsive Design**: Works on desktop and mobile

## Architecture

### Backend (Python/FastAPI)
- FastAPI for REST API
- MultiOn AgentQ integration for intelligent web scraping
- OpenAI for chat functionality
- Async tournament aggregation from multiple sources

### Frontend (React/TypeScript)
- Vite for fast development
- Tailwind CSS for styling
- Lucide React for icons
- XLSX for Excel export

## Setup

### Prerequisites
- Python 3.9+
- Node.js 18+
- MultiOn API key (optional, uses mock data without it)
- OpenAI API key (optional, uses fallback chat without it)

### Backend Setup

```bash
cd backend

# Create virtual environment
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt

# Set environment variables
cp .env.example .env
# Edit .env with your API keys

# Run the server
uvicorn app.main:app --reload --port 8000
```

### Frontend Setup

```bash
cd frontend

# Install dependencies
npm install

# Run development server
npm run dev
```

The frontend will be available at http://localhost:3000 and will proxy API requests to the backend at http://localhost:8000.

## API Endpoints

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/api/chat` | POST | Chat with the AI to search tournaments |
| `/api/tournaments` | GET | Get all tournaments from all sources |
| `/api/tournaments/search` | POST | Search with filters |
| `/api/tournaments/{source}` | GET | Get tournaments from specific source |
| `/api/sources` | GET | List available sources |

## Usage

1. Start both backend and frontend servers
2. Open http://localhost:3000 in your browser
3. Use the chat interface to search for tournaments:
   - "Find tournaments in California"
   - "Show me IBJJF events"
   - "What competitions are in Asia?"
4. Browse the tournament table
5. Filter and sort as needed
6. Click "Export to Excel" to download the data

## Tournament Data

Each tournament includes:
- Name and description
- Date (start and end)
- Location (city, state, country)
- Organizer
- Registration fees
- Registration link
- Source organization
- Sport type

## Development

### Adding New Sources

1. Create a new agent in `backend/app/agents/`
2. Extend `BaseTournamentAgent`
3. Implement `source`, `target_url`, `extraction_prompt`
4. Add to `TournamentService` in `backend/app/services/tournament_service.py`

### Mock Data

The app includes realistic mock data that's used when:
- No MultiOn API key is configured
- API requests fail
- For development and testing

## License

MIT
