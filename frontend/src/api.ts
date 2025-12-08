import { ChatRequest, ChatResponse, Tournament, SearchRequest, Source } from './types';

const API_BASE = '/api';

export async function sendChatMessage(request: ChatRequest): Promise<ChatResponse> {
  const response = await fetch(`${API_BASE}/chat`, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
    },
    body: JSON.stringify(request),
  });

  if (!response.ok) {
    throw new Error('Failed to send chat message');
  }

  return response.json();
}

export async function searchTournaments(request: SearchRequest): Promise<Tournament[]> {
  const response = await fetch(`${API_BASE}/tournaments/search`, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
    },
    body: JSON.stringify(request),
  });

  if (!response.ok) {
    throw new Error('Failed to search tournaments');
  }

  const data = await response.json();
  return data.tournaments;
}

export async function getAllTournaments(): Promise<Tournament[]> {
  const response = await fetch(`${API_BASE}/tournaments`);

  if (!response.ok) {
    throw new Error('Failed to get tournaments');
  }

  return response.json();
}

export async function getSources(): Promise<Source[]> {
  const response = await fetch(`${API_BASE}/sources`);

  if (!response.ok) {
    throw new Error('Failed to get sources');
  }

  const data = await response.json();
  return data.sources;
}
