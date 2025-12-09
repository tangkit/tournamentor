import { useState, useRef, useEffect } from 'react';
import { Send, Bot, User, Loader2 } from 'lucide-react';
import { ChatMessage, Tournament } from '../types';
import { sendChatMessage } from '../api';

interface ChatInterfaceProps {
  onTournamentsReceived: (tournaments: Tournament[]) => void;
}

// Local storage key for recent queries
const RECENT_QUERIES_KEY = 'tournamentor_recent_queries';
const MAX_RECENT_QUERIES = 5;

// Get recent queries from localStorage
const getRecentQueries = (): string[] => {
  try {
    const stored = localStorage.getItem(RECENT_QUERIES_KEY);
    return stored ? JSON.parse(stored) : [];
  } catch {
    return [];
  }
};

// Save a query to recent queries
const saveRecentQuery = (query: string) => {
  try {
    const recent = getRecentQueries();
    // Remove if already exists (to move to front)
    const filtered = recent.filter(q => q.toLowerCase() !== query.toLowerCase());
    // Add to front
    const updated = [query, ...filtered].slice(0, MAX_RECENT_QUERIES);
    localStorage.setItem(RECENT_QUERIES_KEY, JSON.stringify(updated));
  } catch {
    // Ignore localStorage errors
  }
};

export default function ChatInterface({ onTournamentsReceived }: ChatInterfaceProps) {
  const [messages, setMessages] = useState<ChatMessage[]>([
    {
      id: '1',
      role: 'assistant',
      content: "Hello! I'm Tournamentor, your AI assistant for finding BJJ and Judo tournaments. I can search Smoothcomp, IBJJF, ASJJF, and NAGA for upcoming competitions.\n\nTry asking me things like:\n- \"Find tournaments in Malaysia and Taiwan\"\n- \"Show me IBJJF events in USA\"\n- \"What competitions are in Asia in January 2026?\"\n\nHow can I help you find your next competition?",
      timestamp: new Date(),
    },
  ]);
  const [input, setInput] = useState('');
  const [isLoading, setIsLoading] = useState(false);
  const [recentQueries, setRecentQueries] = useState<string[]>([]);
  const messagesEndRef = useRef<HTMLDivElement>(null);

  // Load recent queries on mount
  useEffect(() => {
    setRecentQueries(getRecentQueries());
  }, []);

  const scrollToBottom = () => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  };

  useEffect(() => {
    scrollToBottom();
  }, [messages]);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!input.trim() || isLoading) return;

    const userMessage: ChatMessage = {
      id: Date.now().toString(),
      role: 'user',
      content: input.trim(),
      timestamp: new Date(),
    };

    setMessages((prev) => [...prev, userMessage]);
    setInput('');
    setIsLoading(true);

    // Save to recent queries
    saveRecentQuery(userMessage.content);
    setRecentQueries(getRecentQueries());

    try {
      const history = messages.map((m) => ({
        role: m.role,
        content: m.content,
      }));

      const response = await sendChatMessage({
        message: userMessage.content,
        history,
      });

      const assistantMessage: ChatMessage = {
        id: (Date.now() + 1).toString(),
        role: 'assistant',
        content: response.message,
        timestamp: new Date(),
        tournaments: response.tournaments,
      };

      setMessages((prev) => [...prev, assistantMessage]);

      if (response.tournaments && response.tournaments.length > 0) {
        onTournamentsReceived(response.tournaments);
      }
    } catch (error) {
      console.error('Chat error:', error);
      const errorMessage: ChatMessage = {
        id: (Date.now() + 1).toString(),
        role: 'assistant',
        content: "I'm sorry, I encountered an error. Please try again.",
        timestamp: new Date(),
      };
      setMessages((prev) => [...prev, errorMessage]);
    } finally {
      setIsLoading(false);
    }
  };

  const defaultQueries = [
    "Find tournaments in Malaysia and Taiwan",
    "Show IBJJF events in USA",
    "Asian competitions in January 2026",
    "Smoothcomp tournaments in Singapore",
  ];

  // Show recent queries if available, otherwise show defaults
  const displayQueries = recentQueries.length > 0
    ? recentQueries
    : defaultQueries;

  return (
    <div className="flex flex-col h-full bg-white rounded-xl shadow-lg border border-gray-200">
      {/* Header */}
      <div className="flex items-center gap-3 px-4 py-3 border-b border-gray-200 bg-gradient-to-r from-primary-600 to-primary-700 rounded-t-xl">
        <div className="p-2 bg-white/20 rounded-lg">
          <Bot className="w-5 h-5 text-white" />
        </div>
        <div>
          <h2 className="font-semibold text-white">Tournamentor</h2>
          <p className="text-xs text-primary-100">AI Tournament Finder</p>
        </div>
      </div>

      {/* Messages */}
      <div className="flex-1 overflow-y-auto p-4 space-y-4">
        {messages.map((message) => (
          <div
            key={message.id}
            className={`chat-message flex gap-3 ${
              message.role === 'user' ? 'flex-row-reverse' : ''
            }`}
          >
            <div
              className={`flex-shrink-0 w-8 h-8 rounded-full flex items-center justify-center ${
                message.role === 'user'
                  ? 'bg-primary-600'
                  : 'bg-gray-100'
              }`}
            >
              {message.role === 'user' ? (
                <User className="w-4 h-4 text-white" />
              ) : (
                <Bot className="w-4 h-4 text-primary-600" />
              )}
            </div>
            <div
              className={`max-w-[80%] rounded-2xl px-4 py-2 ${
                message.role === 'user'
                  ? 'bg-primary-600 text-white'
                  : 'bg-gray-100 text-gray-800'
              }`}
            >
              <p className="text-sm whitespace-pre-wrap">{message.content}</p>
              {message.tournaments && message.tournaments.length > 0 && (
                <p className="text-xs mt-2 opacity-70">
                  {message.tournaments.length} tournaments found
                </p>
              )}
            </div>
          </div>
        ))}

        {isLoading && (
          <div className="chat-message flex gap-3">
            <div className="flex-shrink-0 w-8 h-8 rounded-full flex items-center justify-center bg-gray-100">
              <Bot className="w-4 h-4 text-primary-600" />
            </div>
            <div className="bg-gray-100 rounded-2xl px-4 py-3">
              <div className="flex gap-1">
                <div className="typing-dot w-2 h-2 bg-gray-400 rounded-full"></div>
                <div className="typing-dot w-2 h-2 bg-gray-400 rounded-full"></div>
                <div className="typing-dot w-2 h-2 bg-gray-400 rounded-full"></div>
              </div>
            </div>
          </div>
        )}

        <div ref={messagesEndRef} />
      </div>

      {/* Quick queries / Recent searches */}
      {messages.length <= 2 && (
        <div className="px-4 pb-2">
          <p className="text-xs text-gray-500 mb-2">
            {recentQueries.length > 0 ? 'Recent searches:' : 'Try these:'}
          </p>
          <div className="flex flex-wrap gap-2">
            {displayQueries.map((query) => (
              <button
                key={query}
                onClick={() => setInput(query)}
                className="text-xs px-3 py-1.5 bg-gray-100 hover:bg-gray-200 text-gray-700 rounded-full transition-colors"
              >
                {query}
              </button>
            ))}
          </div>
        </div>
      )}

      {/* Input */}
      <form onSubmit={handleSubmit} className="p-4 border-t border-gray-200">
        <div className="flex gap-2">
          <input
            type="text"
            value={input}
            onChange={(e) => setInput(e.target.value)}
            placeholder="Ask about tournaments..."
            className="flex-1 px-4 py-2 border border-gray-300 rounded-full focus:outline-none focus:ring-2 focus:ring-primary-500 focus:border-transparent text-sm"
            disabled={isLoading}
          />
          <button
            type="submit"
            disabled={!input.trim() || isLoading}
            className="px-4 py-2 bg-primary-600 text-white rounded-full hover:bg-primary-700 disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
          >
            {isLoading ? (
              <Loader2 className="w-5 h-5 animate-spin" />
            ) : (
              <Send className="w-5 h-5" />
            )}
          </button>
        </div>
      </form>
    </div>
  );
}
