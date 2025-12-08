import { useState, useMemo } from 'react';
import {
  Download,
  ExternalLink,
  ChevronUp,
  ChevronDown,
  Filter,
  Calendar,
  MapPin,
  DollarSign,
  Building2,
  Search,
  X,
} from 'lucide-react';
import { Tournament, TournamentSource } from '../types';
import * as XLSX from 'xlsx';

interface TournamentTableProps {
  tournaments: Tournament[];
}

type SortField = 'date' | 'name' | 'location' | 'source' | 'organizer';
type SortDirection = 'asc' | 'desc';

const sourceColors: Record<TournamentSource, string> = {
  smoothcomp: 'bg-blue-100 text-blue-800',
  ibjjf: 'bg-red-100 text-red-800',
  asjjf: 'bg-green-100 text-green-800',
  naga: 'bg-purple-100 text-purple-800',
  grappling_industries: 'bg-orange-100 text-orange-800',
  other: 'bg-gray-100 text-gray-800',
};

const sourceNames: Record<TournamentSource, string> = {
  smoothcomp: 'Smoothcomp',
  ibjjf: 'IBJJF',
  asjjf: 'ASJJF',
  naga: 'NAGA',
  grappling_industries: 'Grappling Industries',
  other: 'Other',
};

export default function TournamentTable({ tournaments }: TournamentTableProps) {
  const [sortField, setSortField] = useState<SortField>('date');
  const [sortDirection, setSortDirection] = useState<SortDirection>('asc');
  const [searchQuery, setSearchQuery] = useState('');
  const [sourceFilter, setSourceFilter] = useState<TournamentSource | 'all'>('all');
  const [showFilters, setShowFilters] = useState(false);

  const handleSort = (field: SortField) => {
    if (sortField === field) {
      setSortDirection(sortDirection === 'asc' ? 'desc' : 'asc');
    } else {
      setSortField(field);
      setSortDirection('asc');
    }
  };

  const filteredAndSortedTournaments = useMemo(() => {
    let result = [...tournaments];

    // Apply search filter
    if (searchQuery) {
      const query = searchQuery.toLowerCase();
      result = result.filter(
        (t) =>
          t.name.toLowerCase().includes(query) ||
          t.location.toLowerCase().includes(query) ||
          t.organizer?.toLowerCase().includes(query) ||
          t.description?.toLowerCase().includes(query)
      );
    }

    // Apply source filter
    if (sourceFilter !== 'all') {
      result = result.filter((t) => t.source === sourceFilter);
    }

    // Apply sorting
    result.sort((a, b) => {
      let comparison = 0;
      switch (sortField) {
        case 'date':
          comparison = a.date.localeCompare(b.date);
          break;
        case 'name':
          comparison = a.name.localeCompare(b.name);
          break;
        case 'location':
          comparison = a.location.localeCompare(b.location);
          break;
        case 'source':
          comparison = a.source.localeCompare(b.source);
          break;
        case 'organizer':
          comparison = (a.organizer || '').localeCompare(b.organizer || '');
          break;
      }
      return sortDirection === 'asc' ? comparison : -comparison;
    });

    return result;
  }, [tournaments, searchQuery, sourceFilter, sortField, sortDirection]);

  const exportToExcel = () => {
    const exportData = filteredAndSortedTournaments.map((t) => ({
      'Tournament Name': t.name,
      'Date': t.date,
      'End Date': t.end_date || '',
      'Location': t.location,
      'City': t.city || '',
      'State': t.state || '',
      'Country': t.country || '',
      'Organizer': t.organizer || '',
      'Fees': t.fees || '',
      'Registration Deadline': t.registration_deadline || '',
      'Description': t.description || '',
      'Source': sourceNames[t.source],
      'Sport': t.sport,
      'Registration Link': t.registration_link,
    }));

    const ws = XLSX.utils.json_to_sheet(exportData);
    const wb = XLSX.utils.book_new();
    XLSX.utils.book_append_sheet(wb, ws, 'Tournaments');

    // Auto-size columns
    const maxWidth = 50;
    const cols = Object.keys(exportData[0] || {}).map((key) => ({
      wch: Math.min(
        maxWidth,
        Math.max(
          key.length,
          ...exportData.map((row) => String(row[key as keyof typeof row]).length)
        )
      ),
    }));
    ws['!cols'] = cols;

    XLSX.writeFile(wb, `tournaments_${new Date().toISOString().split('T')[0]}.xlsx`);
  };

  const formatDate = (dateStr: string) => {
    if (dateStr === 'TBD') return 'TBD';
    try {
      const date = new Date(dateStr);
      return date.toLocaleDateString('en-US', {
        month: 'short',
        day: 'numeric',
        year: 'numeric',
      });
    } catch {
      return dateStr;
    }
  };

  const SortIcon = ({ field }: { field: SortField }) => {
    if (sortField !== field) {
      return <ChevronUp className="w-4 h-4 text-gray-300" />;
    }
    return sortDirection === 'asc' ? (
      <ChevronUp className="w-4 h-4 text-primary-600" />
    ) : (
      <ChevronDown className="w-4 h-4 text-primary-600" />
    );
  };

  const uniqueSources = useMemo(() => {
    const sources = new Set(tournaments.map((t) => t.source));
    return Array.from(sources);
  }, [tournaments]);

  if (tournaments.length === 0) {
    return (
      <div className="bg-white rounded-xl shadow-lg border border-gray-200 p-8 text-center">
        <Calendar className="w-16 h-16 text-gray-300 mx-auto mb-4" />
        <h3 className="text-lg font-medium text-gray-700 mb-2">No tournaments yet</h3>
        <p className="text-gray-500">
          Use the chat to search for BJJ and Judo tournaments
        </p>
      </div>
    );
  }

  return (
    <div className="bg-white rounded-xl shadow-lg border border-gray-200 overflow-hidden">
      {/* Header */}
      <div className="px-4 py-3 border-b border-gray-200 bg-gray-50">
        <div className="flex items-center justify-between mb-3">
          <div>
            <h2 className="font-semibold text-gray-800">Tournaments</h2>
            <p className="text-sm text-gray-500">
              {filteredAndSortedTournaments.length} of {tournaments.length} tournaments
            </p>
          </div>
          <button
            onClick={exportToExcel}
            className="flex items-center gap-2 px-4 py-2 bg-green-600 text-white rounded-lg hover:bg-green-700 transition-colors text-sm font-medium"
          >
            <Download className="w-4 h-4" />
            Export to Excel
          </button>
        </div>

        {/* Search and Filters */}
        <div className="flex flex-col sm:flex-row gap-3">
          <div className="relative flex-1">
            <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-gray-400" />
            <input
              type="text"
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
              placeholder="Search tournaments..."
              className="w-full pl-10 pr-4 py-2 border border-gray-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-primary-500 focus:border-transparent text-sm"
            />
            {searchQuery && (
              <button
                onClick={() => setSearchQuery('')}
                className="absolute right-3 top-1/2 -translate-y-1/2"
              >
                <X className="w-4 h-4 text-gray-400 hover:text-gray-600" />
              </button>
            )}
          </div>

          <button
            onClick={() => setShowFilters(!showFilters)}
            className={`flex items-center gap-2 px-4 py-2 border rounded-lg text-sm font-medium transition-colors ${
              showFilters || sourceFilter !== 'all'
                ? 'bg-primary-50 border-primary-300 text-primary-700'
                : 'border-gray-300 text-gray-700 hover:bg-gray-50'
            }`}
          >
            <Filter className="w-4 h-4" />
            Filters
            {sourceFilter !== 'all' && (
              <span className="bg-primary-600 text-white text-xs px-2 py-0.5 rounded-full">
                1
              </span>
            )}
          </button>
        </div>

        {/* Filter Panel */}
        {showFilters && (
          <div className="mt-3 pt-3 border-t border-gray-200">
            <div className="flex flex-wrap gap-2">
              <button
                onClick={() => setSourceFilter('all')}
                className={`px-3 py-1.5 rounded-full text-sm font-medium transition-colors ${
                  sourceFilter === 'all'
                    ? 'bg-primary-600 text-white'
                    : 'bg-gray-100 text-gray-700 hover:bg-gray-200'
                }`}
              >
                All Sources
              </button>
              {uniqueSources.map((source) => (
                <button
                  key={source}
                  onClick={() => setSourceFilter(source)}
                  className={`px-3 py-1.5 rounded-full text-sm font-medium transition-colors ${
                    sourceFilter === source
                      ? 'bg-primary-600 text-white'
                      : `${sourceColors[source]} hover:opacity-80`
                  }`}
                >
                  {sourceNames[source]}
                </button>
              ))}
            </div>
          </div>
        )}
      </div>

      {/* Table */}
      <div className="overflow-x-auto">
        <table className="w-full">
          <thead className="bg-gray-50 border-b border-gray-200">
            <tr>
              <th
                onClick={() => handleSort('date')}
                className="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider cursor-pointer hover:bg-gray-100"
              >
                <div className="flex items-center gap-1">
                  <Calendar className="w-4 h-4" />
                  Date
                  <SortIcon field="date" />
                </div>
              </th>
              <th
                onClick={() => handleSort('name')}
                className="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider cursor-pointer hover:bg-gray-100"
              >
                <div className="flex items-center gap-1">
                  Tournament
                  <SortIcon field="name" />
                </div>
              </th>
              <th
                onClick={() => handleSort('location')}
                className="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider cursor-pointer hover:bg-gray-100"
              >
                <div className="flex items-center gap-1">
                  <MapPin className="w-4 h-4" />
                  Location
                  <SortIcon field="location" />
                </div>
              </th>
              <th
                onClick={() => handleSort('organizer')}
                className="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider cursor-pointer hover:bg-gray-100"
              >
                <div className="flex items-center gap-1">
                  <Building2 className="w-4 h-4" />
                  Organizer
                  <SortIcon field="organizer" />
                </div>
              </th>
              <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">
                <div className="flex items-center gap-1">
                  <DollarSign className="w-4 h-4" />
                  Fees
                </div>
              </th>
              <th
                onClick={() => handleSort('source')}
                className="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider cursor-pointer hover:bg-gray-100"
              >
                <div className="flex items-center gap-1">
                  Source
                  <SortIcon field="source" />
                </div>
              </th>
              <th className="px-4 py-3 text-center text-xs font-medium text-gray-500 uppercase tracking-wider">
                Register
              </th>
            </tr>
          </thead>
          <tbody className="divide-y divide-gray-200">
            {filteredAndSortedTournaments.map((tournament) => (
              <tr key={tournament.id} className="hover:bg-gray-50">
                <td className="px-4 py-4 whitespace-nowrap">
                  <div className="text-sm font-medium text-gray-900">
                    {formatDate(tournament.date)}
                  </div>
                  {tournament.end_date && tournament.end_date !== tournament.date && (
                    <div className="text-xs text-gray-500">
                      to {formatDate(tournament.end_date)}
                    </div>
                  )}
                </td>
                <td className="px-4 py-4">
                  <div className="text-sm font-medium text-gray-900 max-w-xs">
                    {tournament.name}
                  </div>
                  {tournament.description && (
                    <div className="text-xs text-gray-500 mt-1 line-clamp-2 max-w-xs">
                      {tournament.description}
                    </div>
                  )}
                </td>
                <td className="px-4 py-4 whitespace-nowrap">
                  <div className="text-sm text-gray-900">{tournament.location}</div>
                </td>
                <td className="px-4 py-4 whitespace-nowrap">
                  <div className="text-sm text-gray-900">
                    {tournament.organizer || '-'}
                  </div>
                </td>
                <td className="px-4 py-4 whitespace-nowrap">
                  <div className="text-sm text-gray-900">{tournament.fees || '-'}</div>
                </td>
                <td className="px-4 py-4 whitespace-nowrap">
                  <span
                    className={`inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium ${
                      sourceColors[tournament.source]
                    }`}
                  >
                    {sourceNames[tournament.source]}
                  </span>
                </td>
                <td className="px-4 py-4 whitespace-nowrap text-center">
                  <a
                    href={tournament.registration_link}
                    target="_blank"
                    rel="noopener noreferrer"
                    className="inline-flex items-center gap-1 px-3 py-1.5 bg-primary-600 text-white text-xs font-medium rounded-lg hover:bg-primary-700 transition-colors"
                  >
                    Register
                    <ExternalLink className="w-3 h-3" />
                  </a>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      {filteredAndSortedTournaments.length === 0 && (
        <div className="p-8 text-center">
          <p className="text-gray-500">No tournaments match your filters</p>
          <button
            onClick={() => {
              setSearchQuery('');
              setSourceFilter('all');
            }}
            className="mt-2 text-primary-600 hover:text-primary-700 text-sm font-medium"
          >
            Clear filters
          </button>
        </div>
      )}
    </div>
  );
}
