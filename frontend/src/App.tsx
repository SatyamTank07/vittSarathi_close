import { useState, KeyboardEvent } from 'react';
import './App.css';
import Header from './components/Header';
import ChatSidebar from './components/ChatSidebar';
import Dashboard from './components/Dashboard';

function App() {
  const [searchQuery, setSearchQuery] = useState<string>('');
  const [loading, setLoading] = useState<boolean>(false);
  const [error, setError] = useState<string | null>(null);
  const [stockData, setStockData] = useState<any | null>(null);

  // Default quick tickers
  const quickTickers = [
    { label: 'Apple', ticker: 'AAPL' },
    { label: 'Reliance', ticker: 'RELIANCE' },
    { label: 'Nvidia', ticker: 'NVDA' },
    { label: 'TCS', ticker: 'TCS' },
    { label: 'Tesla', ticker: 'TSLA' }
  ];

  // Fetch Stock Data
  const handleSearch = async (tickerToSearch?: string) => {
    const symbol = (tickerToSearch || searchQuery).trim().toUpperCase();
    if (!symbol) return;
    
    setLoading(true);
    setError(null);
    setStockData(null);

    try {
      const response = await fetch(`http://localhost:8000/api/stock/${encodeURIComponent(symbol)}`);
      if (!response.ok) {
        const errData = await response.json();
        throw new Error(errData.detail || 'Failed to fetch stock data.');
      }
      const data = await response.json();
      setStockData(data);
    } catch (err) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  };

  const handleKeyPress = (e: KeyboardEvent<HTMLInputElement>) => {
    if (e.key === 'Enter') {
      handleSearch();
    }
  };

  return (
    <div className="app-container">
      <Header
        searchQuery={searchQuery}
        setSearchQuery={setSearchQuery}
        handleSearch={handleSearch}
        handleKeyPress={handleKeyPress}
        loading={loading}
      />

      {/* Main Layout */}
      <main className="app-main-content split-layout">
        <ChatSidebar />
        <Dashboard
          stockData={stockData}
          loading={loading}
          error={error}
          quickTickers={quickTickers}
          setSearchQuery={setSearchQuery}
          handleSearch={handleSearch}
        />
      </main>

    </div>
  );
}

export default App;
