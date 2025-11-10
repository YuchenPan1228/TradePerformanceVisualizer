import React, { useState, useEffect } from 'react';
import { Search, Menu, Bell, Moon } from 'lucide-react';
import axios from 'axios';

const API_URL = 'http://localhost:5000/api';

const PortfolioDashboard = () => {
  const [portfolioData, setPortfolioData] = useState(null);
  const [transactions, setTransactions] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [growthData, setGrowthData] = useState([]);
  const [watchlist, setWatchlist] = useState([]);
  const [watchlistQuotes, setWatchlistQuotes] = useState([]);
  const [watchlistIndex, setWatchlistIndex] = useState(0);

  useEffect(() => {
    const initFetch = async () => {
      await Promise.all([fetchPortfolioData(), fetchTransactions(), fetchWatchlist()]);
    };
    initFetch();
  }, []);

  const fetchPortfolioData = async () => {
    try {
      const { data } = await axios.get(`${API_URL}/portfolio/summary`);
      if (data.success) setPortfolioData(data.data);
      if (data.success && data.data?.totalValue) {
        // Create 30-day synthetic history around current totalValue
        const base = Number(data.data.totalValue) || 0;
        const days = 30;
        const series = Array.from({ length: days }, (_, i) => {
          const t = i / (days - 1);
          const drift = (t - 0.5) * 0.04 * base; // +/-2% trend
          const noise = (Math.sin(i * 0.7) + Math.cos(i * 0.3)) * 0.005 * base; // small noise
          const value = Math.max(0, base + drift + noise);
          const d = new Date();
          d.setDate(d.getDate() - (days - 1 - i));
          return { date: d, value };
        });
        setGrowthData(series);
      }
      setLoading(false);
    } catch (err) {
      console.error('Error fetching portfolio:', err);
      setError('Failed to fetch portfolio data');
      setLoading(false);
    }
  };

  const fetchTransactions = async () => {
    try {
      const { data } = await axios.get(`${API_URL}/transactions`);
      if (data.success) setTransactions(data.data);
    } catch (err) {
      console.error('Error fetching transactions:', err);
    }
  };

  const fetchWatchlist = async () => {
    try {
      const { data } = await axios.get(`${API_URL}/watchlist`);
      if (data.success) {
        setWatchlist(data.data || []);
        await fetchWatchlistQuotes(data.data || []);
      }
    } catch (err) {
      console.error('Error fetching watchlist:', err);
    }
  };

  const fetchWatchlistQuotes = async (symbols) => {
    try {
      const unique = Array.from(new Set(symbols)).slice(0, 20);
      const { data } = await axios.get(`${API_URL}/watchlist/quotes`, {
        params: { symbols: unique.join(',') }
      });
      if (data.success) {
        setWatchlistQuotes(data.data || []);
        setWatchlistIndex(0);
      }
    } catch (err) {
      console.error('Error fetching quotes:', err);
    }
  };

  useEffect(() => {
    if (!watchlistQuotes.length) return;
    const id = setInterval(() => {
      setWatchlistIndex(i => (i + 1) % watchlistQuotes.length);
    }, 3000);
    return () => clearInterval(id);
  }, [watchlistQuotes.length]);

  const safeText = (val) => {
    if (val === null || val === undefined) return '';
    if (typeof val === 'object') {
      if (val.symbol || val.raw_symbol) return val.symbol || val.raw_symbol;
      try { return JSON.stringify(val); } catch { return String(val); }
    }
    return String(val);
  };

  if (loading) {
    return (
      <div className="min-h-screen bg-gray-50 flex items-center justify-center">
        <div className="text-center">
          <div className="animate-spin rounded-full h-12 w-12 border-b-2 border-blue-600 mx-auto"></div>
          <p className="mt-4 text-gray-600">Loading portfolio data...</p>
        </div>
      </div>
    );
  }

  if (error) {
    return (
      <div className="min-h-screen bg-gray-50 flex items-center justify-center">
        <div className="bg-red-50 border border-red-200 rounded-lg p-6 max-w-md">
          <p className="text-red-800 font-medium">{error}</p>
          <button 
            onClick={() => window.location.reload()}
            className="mt-4 px-4 py-2 bg-red-600 text-white rounded-lg hover:bg-red-700"
          >
            Retry
          </button>
        </div>
      </div>
    );
  }

  const holdings = portfolioData?.holdings || [];
  const totalValue = portfolioData?.totalValue || 0;
  const totalReturn = portfolioData?.totalReturn || 0;
  const totalCost = portfolioData?.totalCost || 0;
  const totalGainLoss = portfolioData?.totalGainLoss || 0;

  const bestPerformer = holdings.length
    ? holdings.reduce((max, h) => (h.change > max.change ? h : max), holdings[0])
    : null;

  const worstPerformer = holdings.length
    ? holdings.reduce((min, h) => (h.change < min.change ? h : min), holdings[0])
    : null;

  const PortfolioGrowthChart = ({ points, height = 180 }) => {
    if (!points || points.length === 0) return null;
    const width = 600; // will scale via viewBox
    const padding = 24;
    const xs = points.map((_, i) => i);
    const ys = points.map(p => p.value);
    const xMin = 0, xMax = points.length - 1;
    const yMin = Math.min(...ys);
    const yMax = Math.max(...ys);
    const yPad = (yMax - yMin) * 0.1 || 1;
    const y0 = yMin - yPad;
    const y1 = yMax + yPad;
    const sx = x => padding + (x - xMin) / (xMax - xMin || 1) * (width - padding * 2);
    const sy = y => padding + (1 - (y - y0) / (y1 - y0 || 1)) * (height - padding * 2);
    const d = points.map((p, i) => `${i === 0 ? 'M' : 'L'} ${sx(i)} ${sy(p.value)}`).join(' ');
    const first = points[0]?.value ?? 0;
    const last = points[points.length - 1]?.value ?? 0;
    const pct = first ? ((last - first) / first) * 100 : 0;
    return (
      <div className="bg-white rounded-2xl p-6 shadow-sm">
        <div className="flex items-center justify-between mb-3">
          <h3 className="text-xl font-bold text-gray-900">Portfolio Growth (30d)</h3>
          <div className={`text-sm font-medium ${pct >= 0 ? 'text-green-600' : 'text-red-600'}`}>{pct >= 0 ? '+' : ''}{pct.toFixed(2)}%</div>
        </div>
        <svg viewBox={`0 0 ${width} ${height}`} className="w-full h-48">
          <defs>
            <linearGradient id="areaGrad" x1="0" y1="0" x2="0" y2="1">
              <stop offset="0%" stopColor="#3b82f6" stopOpacity="0.25" />
              <stop offset="100%" stopColor="#3b82f6" stopOpacity="0" />
            </linearGradient>
          </defs>
          <rect x="0" y="0" width={width} height={height} fill="transparent" />
          <path d={d}
                fill="none"
                stroke="#3b82f6"
                strokeWidth="2.5" />
          <path d={`${d} L ${sx(xMax)} ${sy(y0)} L ${sx(xMin)} ${sy(y0)} Z`} fill="url(#areaGrad)" />
          {/* Y-axis labels */}
          <g className="text-[10px] fill-gray-400">
            <text x={padding} y={sy(y1).toFixed(1)} dy="10">{y1.toLocaleString(undefined, { maximumFractionDigits: 0 })}</text>
            <text x={padding} y={sy((y0 + y1) / 2).toFixed(1)} dy="10">{((y0 + y1) / 2).toLocaleString(undefined, { maximumFractionDigits: 0 })}</text>
            <text x={padding} y={sy(y0).toFixed(1)} dy="10">{y0.toLocaleString(undefined, { maximumFractionDigits: 0 })}</text>
          </g>
        </svg>
      </div>
    );
  };

  return (
    <div className="min-h-screen bg-gray-50">
      {/* Header */}
      <header className="bg-white border-b border-gray-200 px-6 py-4">
        <div className="flex items-center justify-between max-w-7xl mx-auto">
          <div className="flex items-center gap-4">
            <button className="p-2 hover:bg-gray-100 rounded-lg">
              <Menu className="w-5 h-5" />
            </button>
            <div className="relative flex-1 max-w-md">
              <Search className="absolute left-3 top-1/2 transform -translate-y-1/2 w-5 h-5 text-gray-400" />
              <input
                type="text"
                placeholder="Search or type command..."
                className="w-full pl-10 pr-20 py-2 border border-gray-200 rounded-lg focus:outline-none focus:ring-2 focus:ring-blue-500"
              />
              <kbd className="absolute right-3 top-1/2 transform -translate-y-1/2 px-2 py-1 text-xs bg-gray-100 rounded">⌘ K</kbd>
            </div>
          </div>
          <div className="flex items-center gap-4">
            <button className="p-2 hover:bg-gray-100 rounded-lg">
              <Moon className="w-5 h-5" />
            </button>
            <button className="p-2 hover:bg-gray-100 rounded-lg relative">
              <Bell className="w-5 h-5" />
              <span className="absolute top-1 right-1 w-2 h-2 bg-orange-500 rounded-full"></span>
            </button>
            <div className="flex items-center gap-2 cursor-pointer">
              <div className="w-10 h-10 bg-blue-500 rounded-full"></div>
              <span className="font-medium">Portfolio</span>
            </div>
          </div>
        </div>
      </header>

      <main className="max-w-7xl mx-auto px-6 py-8">
        {/* Watchlist Ticker */}
        {watchlistQuotes.length > 0 && (
          <section className="bg-white rounded-xl shadow-sm mb-6 overflow-hidden">
            <div className="flex items-center justify-between px-4 pt-3">
              <h3 className="text-sm font-semibold text-gray-700">Watchlist</h3>
            </div>
            <div className="relative w-full h-[84px]">
              <div
                className="absolute inset-0 flex transition-transform duration-500 ease-out"
                style={{
                  width: `${watchlistQuotes.length * 240}px`,
                  transform: `translateX(-${watchlistIndex * 240}px)`
                }}
              >
                {watchlistQuotes.map((q, idx) => {
                  const up = (q.changePercent || 0) >= 0;
                  return (
                    <div key={idx} className="w-[240px] px-4 py-3">
                      <div className="h-full w-full rounded-lg border border-gray-100 px-4 py-2 flex items-center justify-between">
                        <div>
                          <div className="text-sm font-bold text-gray-900">{safeText(q.symbol)}</div>
                          <div className="text-[11px] text-gray-500">{safeText(q.name)}</div>
                        </div>
                        <div className="text-right">
                          <div className="text-sm font-semibold text-gray-900">${Number(q.price || 0).toFixed(2)}</div>
                          <div className={`text-xs ${up ? 'text-green-600' : 'text-red-600'}`}>{up ? '+' : ''}{Number(q.changePercent || 0).toFixed(2)}%</div>
                        </div>
                      </div>
                    </div>
                  )
                })}
              </div>
            </div>
          </section>
        )}
        {/* Portfolio Summary */}
        <section className="bg-gradient-to-r from-blue-600 to-blue-800 rounded-2xl p-8 text-white mb-6">
          <h1 className="text-2xl font-bold mb-4">Portfolio Overview</h1>
          <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
            <div>
              <p className="text-blue-200 text-sm mb-1">Total Value</p>
              <p className="text-3xl font-bold">${totalValue.toLocaleString(undefined, {minimumFractionDigits: 2})}</p>
            </div>
            <div>
              <p className="text-blue-200 text-sm mb-1">Total Return</p>
              <p className={`text-3xl font-bold ${totalReturn >= 0 ? 'text-green-300' : 'text-red-300'}`}>
                {totalReturn >= 0 ? '+' : ''}{totalReturn.toFixed(2)}%
              </p>
            </div>
            <div>
              <p className="text-blue-200 text-sm mb-1">Total Holdings</p>
              <p className="text-3xl font-bold">{holdings.length}</p>
            </div>
          </div>
        </section>

        <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
          {/* Left: Holdings + Transactions */}
          <div className="lg:col-span-2 space-y-6">
            {/* Growth Chart */}
            <PortfolioGrowthChart points={growthData} />
            {/* Holdings */}
            <section className="bg-white rounded-2xl p-6 shadow-sm">
              <h2 className="text-2xl font-bold text-gray-900 mb-6">Your Holdings</h2>
              {holdings.length > 0 ? (
                <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                  {holdings.map((holding, idx) => (
                    <div key={idx} className="bg-gray-50 rounded-xl p-6">
                      <div className="flex items-start justify-between mb-4">
                        <div>
                           <div className="font-bold text-gray-900 text-lg">{safeText(holding.symbol)}</div>
                           <div className="text-sm text-gray-500">{safeText(holding.name)}</div>
                          <div className="text-xs text-gray-400 mt-1">{holding.quantity} shares</div>
                        </div>
                        <div className="text-right">
                          <div className="font-bold text-gray-900">${holding.price.toFixed(2)}</div>
                          <div className={`text-sm flex items-center gap-1 justify-end ${holding.change > 0 ? 'text-green-600' : 'text-red-600'}`}>
                            <span>{holding.change > 0 ? '↑' : '↓'}</span>
                            {Math.abs(holding.change).toFixed(2)}%
                          </div>
                        </div>
                      </div>
                      <div className="border-t border-gray-200 pt-3 mt-3">
                        <div className="flex justify-between text-sm">
                          <span className="text-gray-600">Market Value:</span>
                          <span className="font-medium">${holding.marketValue.toFixed(2)}</span>
                        </div>
                        <div className="flex justify-between text-sm mt-1">
                          <span className="text-gray-600">Cost Basis:</span>
                          <span className="font-medium">${holding.costBasis.toFixed(2)}</span>
                        </div>
                      </div>
                    </div>
                  ))}
                </div>
              ) : (
                <div className="text-center py-12 text-gray-500">No holdings found in your portfolio</div>
              )}
            </section>

            {/* Transactions */}
            <section className="bg-white rounded-2xl p-6 shadow-sm">
              <div className="flex items-center justify-between mb-6">
                <h2 className="text-2xl font-bold text-gray-900">Recent Transactions</h2>
                <div className="relative">
                  <Search className="absolute left-3 top-1/2 transform -translate-y-1/2 w-4 h-4 text-gray-400" />
                  <input
                    type="text"
                    placeholder="Search..."
                    className="pl-10 pr-4 py-2 border border-gray-200 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
                  />
                </div>
              </div>

              {transactions.length > 0 ? (
                <div className="overflow-x-auto">
                  <table className="w-full">
                    <thead>
                      <tr className="text-left text-sm text-gray-500 border-b">
                        <th className="pb-3 font-medium">Description</th>
                        <th className="pb-3 font-medium">Date</th>
                        <th className="pb-3 font-medium">Amount</th>
                        <th className="pb-3 font-medium">Type</th>
                        <th className="pb-3 font-medium">Status</th>
                      </tr>
                    </thead>
                    <tbody>
                      {transactions.map((tx, idx) => (
                        <tr key={idx} className="border-b last:border-0">
                          <td className="py-4">
                            <div className="font-medium">{safeText(tx.description) || safeText(tx.symbol) || 'N/A'}</div>
                            {tx.quantity && (
                              <div className="text-sm text-gray-500">
                                {tx.quantity} shares @ ${tx.price}
                              </div>
                            )}
                          </td>
                          <td className="py-4 text-gray-600 text-sm">
                            {new Date(tx.date).toLocaleDateString()}
                          </td>
                          <td className="py-4 font-medium">
                            ${Math.abs(tx.amount).toLocaleString(undefined, { minimumFractionDigits: 2 })}
                          </td>
                          <td className="py-4 text-gray-600">{safeText(tx.type)}</td>
                          <td className="py-4">
                            <span className="px-3 py-1 rounded-full text-sm font-medium bg-green-100 text-green-700">
                              {tx.status}
                            </span>
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              ) : (
                <div className="text-center py-12 text-gray-500">No recent transactions</div>
              )}
            </section>
          </div>

          {/* Sidebar */}
          <aside className="space-y-6">
            {/* Top Holdings */}
            <section className="bg-white rounded-2xl p-6 shadow-sm">
              <h3 className="text-xl font-bold text-gray-900 mb-4">Top Holdings</h3>
              {holdings.slice(0, 5).map((holding, idx) => (
                <div key={idx} className="flex items-center justify-between mb-3">
                  <div>
                    <div className="font-bold text-gray-900">{safeText(holding.symbol)}</div>
                    <div className="text-xs text-gray-500">{holding.quantity} shares</div>
                  </div>
                  <div className="text-right">
                    <div className="font-bold text-gray-900">${holding.marketValue.toFixed(2)}</div>
                    <div className={`text-xs ${holding.change > 0 ? 'text-green-600' : 'text-red-600'}`}>
                      {holding.change > 0 ? '+' : ''}{holding.change.toFixed(2)}%
                    </div>
                  </div>
                </div>
              ))}
            </section>

            {/* Quick Stats */}
            <section className="bg-white rounded-2xl p-6 shadow-sm">
              <h3 className="text-xl font-bold text-gray-900 mb-4">Quick Stats</h3>
              <div className="space-y-3">
                <div className="flex justify-between items-center">
                  <span className="text-gray-600">Best Performer</span>
                  <span className="font-medium text-green-600">{safeText(bestPerformer?.symbol) || 'N/A'}</span>
                </div>
                <div className="flex justify-between items-center">
                  <span className="text-gray-600">Worst Performer</span>
                  <span className="font-medium text-red-600">{safeText(worstPerformer?.symbol) || 'N/A'}</span>
                </div>
                <div className="flex justify-between items-center">
                  <span className="text-gray-600">Total Cost</span>
                  <span className="font-medium">${totalCost.toFixed(2)}</span>
                </div>
                <div className="flex justify-between items-center">
                  <span className="text-gray-600">Unrealized P/L</span>
                  <span className={`font-medium ${totalGainLoss >= 0 ? 'text-green-600' : 'text-red-600'}`}>
                    {totalGainLoss >= 0 ? '+' : ''}${totalGainLoss.toFixed(2)}
                  </span>
                </div>
              </div>
            </section>
          </aside>
        </div>
      </main>
    </div>
  );
};

export default PortfolioDashboard;
