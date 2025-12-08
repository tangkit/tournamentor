export type TournamentSource =
  | 'smoothcomp'
  | 'asjjf'
  | 'ibjjf'
  | 'naga'
  | 'grappling_industries'
  | 'other';

export interface Tournament {
  id: string;
  name: string;
  date: string;
  end_date?: string;
  location: string;
  city?: string;
  state?: string;
  country?: string;
  description?: string;
  organizer?: string;
  fees?: string;
  registration_link: string;
  source: TournamentSource;
  sport: string;
  registration_deadline?: string;
  scraped_at?: string;
}

export interface ChatMessage {
  id: string;
  role: 'user' | 'assistant';
  content: string;
  timestamp: Date;
  tournaments?: Tournament[];
}

export interface ChatRequest {
  message: string;
  history: { role: string; content: string }[];
}

export interface ChatResponse {
  message: string;
  tournaments: Tournament[];
}

export interface SearchRequest {
  query?: string;
  sources?: TournamentSource[];
  location?: string;
  date_from?: string;
  date_to?: string;
}

export interface Source {
  id: string;
  name: string;
  url: string;
}
