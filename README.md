# Tournamentor

AI-powered BJJ and Judo tournament aggregator with a chat-style interface and Playwright-based web scraping.

## Features

- **Chat-Style AI Interface**: Conversational search for tournaments
- **Multi-Source Aggregation**: Pulls tournaments from:
  - Smoothcomp (requires login)
  - IBJJF (requires login)
  - ASJJF (requires login)
  - NAGA (public)
  - Grappling Industries (public)
- **Playwright-Based Scraping**: Real browser automation for reliable data extraction
- **Session Persistence**: Login sessions are saved for faster subsequent scrapes
- **Smart Filtering**: Filter by location, date, source, and more
- **Sortable Table**: Sort tournaments by any column
- **Excel Export**: Export tournament data to Excel spreadsheet
- **Responsive Design**: Works on desktop and mobile

## Architecture

### Backend (Python/FastAPI)
- FastAPI for REST API
- **Playwright** for browser automation and web scraping
- **BeautifulSoup** for HTML parsing
- OpenAI for chat functionality
- Async tournament aggregation from multiple sources
- Session state persistence for authenticated sites

### Frontend (React/TypeScript)
- Vite for fast development
- Tailwind CSS for styling
- Lucide React for icons
- XLSX for Excel export

## Setup

### Prerequisites
- Python 3.9+
- Node.js 18+
- OpenAI API key (optional, uses fallback chat without it)

### Backend Setup

```bash
cd backend

# Create virtual environment
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt

# Install Playwright browsers
playwright install chromium

# Set environment variables
cp .env.example .env
# Edit .env with your credentials
```

### Environment Variables

Edit `.env` with your credentials:

```env
# OpenAI API Key (for chat functionality)
OPENAI_API_KEY=your_openai_api_key_here

# Smoothcomp Credentials
SMOOTHCOMP_EMAIL=your_smoothcomp_email
SMOOTHCOMP_PASSWORD=your_smoothcomp_password

# IBJJF Credentials
IBJJF_EMAIL=your_ibjjf_email
IBJJF_PASSWORD=your_ibjjf_password

# ASJJF Credentials
ASJJF_EMAIL=your_asjjf_email
ASJJF_PASSWORD=your_asjjf_password

# Browser Settings
HEADLESS=true
BROWSER_TIMEOUT=30000
```

### Run the Backend

```bash
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
| `/health` | GET | Health check |

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

## How It Works

### Scraping Flow

1. **Session Check**: The agent checks if a valid session exists
2. **Login (if needed)**: If no session or credentials required, performs login
3. **Navigate**: Goes to the events page
4. **Scroll**: Scrolls to load dynamic content
5. **Parse**: Uses BeautifulSoup to extract tournament data
6. **Save Session**: Saves cookies/localStorage for future use

### Sources

| Source | Login Required | Notes |
|--------|---------------|-------|
| Smoothcomp | Yes | Large tournament database |
| IBJJF | Yes | Official IBJJF events |
| ASJJF | Yes | Asian tournaments |
| NAGA | No | North American events |
| Grappling Industries | No | Round-robin format events |

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
3. Implement required properties:
   - `source` - TournamentSource enum
   - `base_url` - Site base URL
   - `events_url` - Events page URL
   - `login_url` - Login page URL
   - `email_env_var` - Environment variable for email
   - `password_env_var` - Environment variable for password
4. Implement required methods:
   - `_check_logged_in(page)` - Check if logged in
   - `_login(page, context)` - Perform login
   - `_scrape_events_page(page, location)` - Scrape tournaments
   - `_get_mock_data()` - Return mock data for testing
5. Add to `TournamentService` in `backend/app/services/tournament_service.py`

### Mock Data

The app includes realistic mock data that's used when:
- No credentials are configured for a source
- Login fails
- Scraping encounters errors
- For development and testing

### Running Without Credentials

The app works without any credentials - it will use mock data for all sources that require login, and attempt real scraping for public sources (NAGA, Grappling Industries).

## Troubleshooting

### Browser Issues

```bash
# Reinstall Playwright browsers
playwright install chromium --force
```

### Login Failures

- Check your credentials in `.env`
- Try setting `HEADLESS=false` to see what's happening
- Check if the site's login page structure has changed

### Timeout Issues

Increase the timeout in `.env`:
```env
BROWSER_TIMEOUT=60000
```

## License

MIT
