import { useState, useEffect } from 'react';
import { Award, RefreshCw, Info } from 'lucide-react';
import ChatInterface from './components/ChatInterface';
import TournamentTable from './components/TournamentTable';
import { Tournament } from './types';
import { getAllTournaments } from './api';

function App() {
  const [tournaments, setTournaments] = useState<Tournament[]>([]);
  const [isLoading, setIsLoading] = useState(false);
  const [showInfo, setShowInfo] = useState(false);

  const handleTournamentsReceived = (newTournaments: Tournament[]) => {
    setTournaments(newTournaments);
  };

  const loadAllTournaments = async () => {
    setIsLoading(true);
    try {
      const allTournaments = await getAllTournaments();
      setTournaments(allTournaments);
    } catch (error) {
      console.error('Failed to load tournaments:', error);
    } finally {
      setIsLoading(false);
    }
  };

  return (
    <div className="min-h-screen bg-gradient-to-br from-gray-50 to-gray-100">
      {/* Header */}
      <header className="bg-white shadow-sm border-b border-gray-200">
        <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-4">
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-3">
              <div className="p-2 bg-primary-100 rounded-xl">
                <Award className="w-8 h-8 text-primary-600" />
              </div>
              <div>
                <h1 className="text-2xl font-bold text-gray-900">Tournamentor</h1>
                <p className="text-sm text-gray-500">BJJ & Judo Tournament Finder</p>
              </div>
            </div>
            <div className="flex items-center gap-3">
              <button
                onClick={loadAllTournaments}
                disabled={isLoading}
                className="flex items-center gap-2 px-4 py-2 bg-gray-100 text-gray-700 rounded-lg hover:bg-gray-200 transition-colors text-sm font-medium disabled:opacity-50"
              >
                <RefreshCw className={`w-4 h-4 ${isLoading ? 'animate-spin' : ''}`} />
                Load All
              </button>
              <button
                onClick={() => setShowInfo(!showInfo)}
                className="p-2 text-gray-500 hover:text-gray-700 hover:bg-gray-100 rounded-lg transition-colors"
              >
                <Info className="w-5 h-5" />
              </button>
            </div>
          </div>

          {/* Info Panel */}
          {showInfo && (
            <div className="mt-4 p-4 bg-primary-50 rounded-lg border border-primary-100">
              <h3 className="font-medium text-primary-800 mb-2">About Tournamentor</h3>
              <p className="text-sm text-primary-700 mb-3">
                Tournamentor uses AI-powered agents to aggregate BJJ and Judo tournaments from multiple sources:
              </p>
              <div className="flex flex-wrap gap-2">
                <span className="px-2 py-1 bg-blue-100 text-blue-800 rounded text-xs font-medium">
                  Smoothcomp
                </span>
                <span className="px-2 py-1 bg-red-100 text-red-800 rounded text-xs font-medium">
                  IBJJF
                </span>
                <span className="px-2 py-1 bg-green-100 text-green-800 rounded text-xs font-medium">
                  ASJJF
                </span>
                <span className="px-2 py-1 bg-purple-100 text-purple-800 rounded text-xs font-medium">
                  NAGA
                </span>
                <span className="px-2 py-1 bg-orange-100 text-orange-800 rounded text-xs font-medium">
                  Grappling Industries
                </span>
              </div>
              <p className="text-xs text-primary-600 mt-3">
                Powered by MultiOn AgentQ for intelligent web scraping
              </p>
            </div>
          )}
        </div>
      </header>

      {/* Main Content */}
      <main className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-6">
        <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
          {/* Chat Panel */}
          <div className="lg:col-span-1 h-[600px]">
            <ChatInterface onTournamentsReceived={handleTournamentsReceived} />
          </div>

          {/* Tournament Table */}
          <div className="lg:col-span-2">
            <TournamentTable tournaments={tournaments} />
          </div>
        </div>

        {/* Stats */}
        {tournaments.length > 0 && (
          <div className="mt-6 grid grid-cols-2 md:grid-cols-4 gap-4">
            <div className="bg-white rounded-xl p-4 shadow-sm border border-gray-200">
              <p className="text-2xl font-bold text-primary-600">{tournaments.length}</p>
              <p className="text-sm text-gray-500">Total Tournaments</p>
            </div>
            <div className="bg-white rounded-xl p-4 shadow-sm border border-gray-200">
              <p className="text-2xl font-bold text-green-600">
                {new Set(tournaments.map((t) => t.country)).size}
              </p>
              <p className="text-sm text-gray-500">Countries</p>
            </div>
            <div className="bg-white rounded-xl p-4 shadow-sm border border-gray-200">
              <p className="text-2xl font-bold text-blue-600">
                {new Set(tournaments.map((t) => t.source)).size}
              </p>
              <p className="text-sm text-gray-500">Sources</p>
            </div>
            <div className="bg-white rounded-xl p-4 shadow-sm border border-gray-200">
              <p className="text-2xl font-bold text-purple-600">
                {new Set(tournaments.map((t) => t.organizer)).size}
              </p>
              <p className="text-sm text-gray-500">Organizers</p>
            </div>
          </div>
        )}
      </main>

      {/* Footer */}
      <footer className="mt-auto py-6 text-center text-sm text-gray-500">
        <p>Tournamentor - Find your next BJJ or Judo competition</p>
      </footer>
    </div>
  );
}

export default App;
