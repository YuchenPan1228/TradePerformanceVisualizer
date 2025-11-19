import React, { useState, useEffect } from 'react';
import { Search, Menu, Bell, Moon, LogOut } from 'lucide-react';
import axios from 'axios';
import Login from './Login';

const API_URL = 'http://localhost:5001/api';

const PortfolioDashboard = () => {
  const [isAuthenticated, setIsAuthenticated] = useState(false);
  const [username, setUsername] = useState('');
  const [checkingAuth, setCheckingAuth] = useState(true);
  const [portfolioData, setPortfolioData] = useState(null);
  const [transactions, setTransactions] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [growthData, setGrowthData] = useState([]);
  const [watchlist, setWatchlist] = useState([]);
  const [watchlistQuotes, setWatchlistQuotes] = useState([]);
  const [watchlistIndex, setWatchlistIndex] = useState(0);
  
  // Performance graph controls
  const [yAxisType, setYAxisType] = useState('dollar'); // 'dollar' or 'return'
  const [benchmark, setBenchmark] = useState('none'); // 'none', 'SPY', 'custom'
  const [portfolioFilter, setPortfolioFilter] = useState('whole'); // 'whole' or 'risk'
  const [benchmarkData, setBenchmarkData] = useState([]);
  const [timeframe, setTimeframe] = useState(30); // days
  const [availableStocks, setAvailableStocks] = useState([]);
  const [selectedStocks, setSelectedStocks] = useState(new Set()); // Set of selected stock symbols
  const [showStockFilter, setShowStockFilter] = useState(false);
  const [hoveredPoint, setHoveredPoint] = useState(null); // {x, y, date, portfolioValue, benchmarkValue}

  useEffect(() => {
    checkAuthStatus();
  }, []);

  useEffect(() => {
    if (isAuthenticated) {
      const initFetch = async () => {
        await Promise.all([fetchPortfolioData(), fetchTransactions(), fetchWatchlist(), fetchPortfolioHistory(), fetchPortfolioStocks()]);
      };
      initFetch();
    }
  }, [isAuthenticated]);

  const checkAuthStatus = async () => {
    try {
      const { data } = await axios.get(`${API_URL}/auth/status`, {
        withCredentials: true
      });
      if (data.success && data.logged_in) {
        setIsAuthenticated(true);
        setUsername(data.username);
      }
    } catch (err) {
      console.error('Error checking auth status:', err);
    } finally {
      setCheckingAuth(false);
    }
  };

  const handleLogin = (loggedInUsername) => {
    setIsAuthenticated(true);
    setUsername(loggedInUsername);
  };

  const handleLogout = async () => {
    try {
      await axios.post(`${API_URL}/auth/logout`, {}, { withCredentials: true });
      setIsAuthenticated(false);
      setUsername('');
    } catch (err) {
      console.error('Error logging out:', err);
    }
  };

  const fetchPortfolioStocks = async () => {
    try {
      const { data } = await axios.get(`${API_URL}/portfolio/stocks`, {
        withCredentials: true
      });
      if (data.success) {
        setAvailableStocks(data.data || []);
        // Select all stocks by default
        setSelectedStocks(new Set(data.data.map(s => s.symbol)));
      }
    } catch (err) {
      console.error('Error fetching portfolio stocks:', err);
    }
  };

  const fetchPortfolioData = async () => {
    try {
      const { data } = await axios.get(`${API_URL}/portfolio/summary`, {
        withCredentials: true
      });
      if (data.success) setPortfolioData(data.data);
      setLoading(false);
    } catch (err) {
      console.error('Error fetching portfolio:', err);
      setError('Failed to fetch portfolio data');
      setLoading(false);
    }
  };

  const fetchPortfolioHistory = async () => {
    try {
      const symbols = selectedStocks.size > 0 && selectedStocks.size < availableStocks.length
        ? Array.from(selectedStocks).join(',')
        : '';
      
      const { data } = await axios.get(`${API_URL}/portfolio/history`, {
        params: { 
          days: timeframe,
          daily: 'true', // Use daily reconstruction
          ...(symbols && { symbols })
        },
        withCredentials: true
      });
      if (data.success && data.data) {
        // Transform the data to match the chart format
        const series = data.data.map(item => ({
          date: new Date(item.date),
          value: Number(item.value) || 0
        }));
        setGrowthData(series);
      }
    } catch (err) {
      console.error('Error fetching portfolio history:', err);
    }
  };

  const fetchBenchmarkData = async (symbol) => {
    if (!symbol || symbol === 'none') {
      setBenchmarkData([]);
      return;
    }
    try {
      const { data } = await axios.get(`${API_URL}/benchmark/history`, {
        params: { symbol, days: timeframe },
        withCredentials: true
      });
      if (data.success && data.data) {
        const series = data.data.map(item => ({
          date: new Date(item.date),
          value: Number(item.value) || 0
        }));
        setBenchmarkData(series);
      }
    } catch (err) {
      console.error('Error fetching benchmark data:', err);
      setBenchmarkData([]);
    }
  };

  useEffect(() => {
    fetchPortfolioHistory();
    if (benchmark !== 'none') {
      fetchBenchmarkData(benchmark === 'custom' ? 'SPY' : benchmark);
    } else {
      setBenchmarkData([]);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [timeframe, benchmark, selectedStocks]);

  const fetchTransactions = async () => {
    try {
      const { data } = await axios.get(`${API_URL}/transactions`, {
        withCredentials: true
      });
      if (data.success) setTransactions(data.data);
    } catch (err) {
      console.error('Error fetching transactions:', err);
    }
  };

  const fetchWatchlist = async () => {
    try {
      const { data } = await axios.get(`${API_URL}/watchlist`, {
        withCredentials: true
      });
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
        params: { symbols: unique.join(',') },
        withCredentials: true
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

  if (checkingAuth) {
    return (
      <div className="min-h-screen bg-gray-50 flex items-center justify-center">
        <div className="text-center">
          <div className="animate-spin rounded-full h-12 w-12 border-b-2 border-blue-600 mx-auto"></div>
          <p className="mt-4 text-gray-600">Checking authentication...</p>
        </div>
      </div>
    );
  }

  if (!isAuthenticated) {
    return <Login onLogin={handleLogin} />;
  }

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

  // Calculate returns from dollar values
  const calculateReturns = (data) => {
    if (!data || data.length === 0) return [];
    const firstValue = data[0].value;
    if (!firstValue || firstValue === 0) return data.map(d => ({ ...d, value: 0 }));
    return data.map(d => ({
      ...d,
      value: ((d.value - firstValue) / firstValue) * 100
    }));
  };

  // Normalize benchmark data to start at same point as portfolio for comparison
  const normalizeBenchmark = (portfolioData, benchmarkData) => {
    if (!portfolioData || portfolioData.length === 0 || !benchmarkData || benchmarkData.length === 0) return benchmarkData;
    const portfolioFirst = portfolioData[0].value;
    const benchmarkFirst = benchmarkData[0].value;
    if (!portfolioFirst || !benchmarkFirst || benchmarkFirst === 0) return benchmarkData;
    const scale = portfolioFirst / benchmarkFirst;
    return benchmarkData.map(d => ({ ...d, value: d.value * scale }));
  };

  const PerformanceGraph = () => {
    const height = 400;
    const width = 800;
    const padding = 60;
    
    // Prepare portfolio data
    let portfolioPoints = growthData || [];
    if (yAxisType === 'return') {
      portfolioPoints = calculateReturns(portfolioPoints);
    }
    
    // Prepare benchmark data
    let benchmarkPoints = benchmarkData || [];
    if (benchmarkPoints.length > 0) {
      if (yAxisType === 'return') {
        benchmarkPoints = calculateReturns(benchmarkPoints);
      } else {
        // Normalize benchmark to portfolio scale for dollar comparison
        benchmarkPoints = normalizeBenchmark(portfolioPoints, benchmarkPoints);
      }
    }
    
    // Combine and sort all dates
    const allDates = [...new Set([
      ...portfolioPoints.map(p => p.date.getTime()),
      ...benchmarkPoints.map(p => p.date.getTime())
    ])].sort((a, b) => a - b);
    
    if (allDates.length === 0) {
      return (
        <div className="bg-white rounded-2xl p-6 shadow-sm">
          <div className="text-center py-12 text-gray-500">No data available</div>
        </div>
      );
    }
    
    // Interpolate values for missing dates
    const getValueAtDate = (data, date) => {
      const sorted = [...data].sort((a, b) => a.date - b.date);
      for (let i = 0; i < sorted.length; i++) {
        if (sorted[i].date.getTime() >= date) {
          if (i === 0) return sorted[0].value;
          // Linear interpolation
          const prev = sorted[i - 1];
          const curr = sorted[i];
          const ratio = (date - prev.date.getTime()) / (curr.date.getTime() - prev.date.getTime());
          return prev.value + (curr.value - prev.value) * ratio;
        }
      }
      return sorted[sorted.length - 1]?.value || 0;
    };
    
    const portfolioSeries = allDates.map(date => ({
      date: new Date(date),
      value: getValueAtDate(portfolioPoints, date)
    }));
    
    const benchmarkSeries = benchmarkPoints.length > 0 ? allDates.map(date => ({
      date: new Date(date),
      value: getValueAtDate(benchmarkPoints, date)
    })) : [];
    
    // Calculate Y-axis range
    const allValues = [
      ...portfolioSeries.map(p => p.value),
      ...benchmarkSeries.map(p => p.value)
    ].filter(v => !isNaN(v) && isFinite(v));
    
    if (allValues.length === 0) {
      return (
        <div className="bg-white rounded-2xl p-6 shadow-sm">
          <div className="text-center py-12 text-gray-500">No valid data points</div>
        </div>
      );
    }
    
    const yMin = Math.min(...allValues);
    const yMax = Math.max(...allValues);
    const yPad = (yMax - yMin) * 0.1 || 1;
    const y0 = yMin - yPad;
    const y1 = yMax + yPad;
    
    const sx = (i) => padding + (i / (allDates.length - 1 || 1)) * (width - padding * 2);
    const sy = (y) => padding + (1 - (y - y0) / (y1 - y0 || 1)) * (height - padding * 2);
    
    const portfolioPath = portfolioSeries.map((p, i) => 
      `${i === 0 ? 'M' : 'L'} ${sx(i)} ${sy(p.value)}`
    ).join(' ');
    
    const benchmarkPath = benchmarkSeries.length > 0 ? benchmarkSeries.map((p, i) => 
      `${i === 0 ? 'M' : 'L'} ${sx(i)} ${sy(p.value)}`
    ).join(' ') : '';
    
    const firstPortfolio = portfolioSeries[0]?.value ?? 0;
    const lastPortfolio = portfolioSeries[portfolioSeries.length - 1]?.value ?? 0;
    const portfolioReturn = firstPortfolio ? ((lastPortfolio - firstPortfolio) / Math.abs(firstPortfolio)) * 100 : 0;
    
    const formatYValue = (val) => {
      if (yAxisType === 'return') {
        return `${val >= 0 ? '+' : ''}${val.toFixed(2)}%`;
      }
      return `$${val.toLocaleString(undefined, { maximumFractionDigits: 0 })}`;
    };
    
    return (
      <div className="bg-white rounded-2xl p-6 shadow-sm">
        {/* Header with stock name and value */}
        <div className="mb-6">
          <h2 className="text-2xl font-bold text-gray-900 mb-2">Portfolio Performance</h2>
          <div className="text-3xl font-bold text-gray-900 mb-1">
            {yAxisType === 'return' 
              ? `${portfolioReturn >= 0 ? '+' : ''}${portfolioReturn.toFixed(2)}%`
              : `$${lastPortfolio.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`
            }
          </div>
          <div className={`text-sm ${portfolioReturn >= 0 ? 'text-green-600' : 'text-red-600'}`}>
            {portfolioReturn >= 0 ? '+' : ''}{portfolioReturn.toFixed(2)}% ({portfolioReturn >= 0 ? '+' : ''}{(lastPortfolio - firstPortfolio).toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })}) Today
          </div>
          <div className="text-xs text-gray-500 mt-1">
            Closed: {new Date().toLocaleString('en-US', { month: 'short', day: 'numeric', hour: 'numeric', minute: 'numeric', timeZoneName: 'short' })}
          </div>
        </div>
        
        <div className="border-t border-gray-200 pt-4 mb-4"></div>
        
        {/* Controls */}
        <div className="mb-6 space-y-4">
          <div className="flex flex-wrap gap-4 items-center">
            <div className="flex items-center gap-2">
              <label className="text-sm font-medium text-gray-700">Portfolio:</label>
              <select
                value={portfolioFilter}
                onChange={(e) => setPortfolioFilter(e.target.value)}
                className="px-3 py-1.5 border border-gray-300 rounded-md text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
              >
                <option value="whole">Whole Portfolio</option>
                <option value="risk">Risk Portfolio Only</option>
              </select>
            </div>
            
            <div className="flex items-center gap-2">
              <label className="text-sm font-medium text-gray-700">Y-axis:</label>
              <select
                value={yAxisType}
                onChange={(e) => setYAxisType(e.target.value)}
                className="px-3 py-1.5 border border-gray-300 rounded-md text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
              >
                <option value="dollar">Dollar Value</option>
                <option value="return">Return (%)</option>
              </select>
            </div>
            
            <div className="flex items-center gap-2">
              <label className="text-sm font-medium text-gray-700">Benchmark:</label>
              <select
                value={benchmark}
                onChange={(e) => setBenchmark(e.target.value)}
                className="px-3 py-1.5 border border-gray-300 rounded-md text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
              >
                <option value="none">None</option>
                <option value="SPY">Market Index (SPY)</option>
                <option value="custom">Custom Portfolio</option>
              </select>
            </div>
            
            <button
              onClick={() => setShowStockFilter(!showStockFilter)}
              className="px-3 py-1.5 border border-gray-300 rounded-md text-sm hover:bg-gray-50 focus:outline-none focus:ring-2 focus:ring-blue-500"
            >
              {showStockFilter ? 'Hide' : 'Select Stocks'} ({selectedStocks.size}/{availableStocks.length})
            </button>
          </div>
          
          {/* Stock Selection Checkboxes */}
          {showStockFilter && (
            <div className="bg-gray-50 rounded-lg p-4 border border-gray-200">
              <div className="flex items-center justify-between mb-3">
                <label className="text-sm font-medium text-gray-700">Select Stocks to Include:</label>
                <div className="flex gap-2">
                  <button
                    onClick={() => setSelectedStocks(new Set(availableStocks.map(s => s.symbol)))}
                    className="text-xs px-2 py-1 text-blue-600 hover:text-blue-800"
                  >
                    Select All
                  </button>
                  <button
                    onClick={() => setSelectedStocks(new Set())}
                    className="text-xs px-2 py-1 text-blue-600 hover:text-blue-800"
                  >
                    Clear All
                  </button>
                </div>
              </div>
              <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-4 gap-3 max-h-48 overflow-y-auto">
                {availableStocks.map((stock) => (
                  <label key={stock.symbol} className="flex items-center gap-2 cursor-pointer hover:bg-white p-2 rounded">
                    <input
                      type="checkbox"
                      checked={selectedStocks.has(stock.symbol)}
                      onChange={(e) => {
                        const newSelected = new Set(selectedStocks);
                        if (e.target.checked) {
                          newSelected.add(stock.symbol);
                        } else {
                          newSelected.delete(stock.symbol);
                        }
                        setSelectedStocks(newSelected);
                      }}
                      className="w-4 h-4 text-blue-600 border-gray-300 rounded focus:ring-blue-500"
                    />
                    <div className="flex-1 min-w-0">
                      <div className="text-sm font-medium text-gray-900 truncate">{stock.symbol}</div>
                      <div className="text-xs text-gray-500 truncate">{stock.name}</div>
                    </div>
                  </label>
                ))}
              </div>
            </div>
          )}
        </div>
        
        {/* Graph */}
        <div className="bg-gray-50 rounded-lg p-4 relative">
          <svg 
            viewBox={`0 0 ${width} ${height}`} 
            className="w-full" 
            style={{ minHeight: '400px' }}
            onMouseLeave={() => setHoveredPoint(null)}
          >
            <defs>
              <linearGradient id="portfolioGrad" x1="0" y1="0" x2="0" y2="1">
                <stop offset="0%" stopColor="#3b82f6" stopOpacity="0.25" />
                <stop offset="100%" stopColor="#3b82f6" stopOpacity="0" />
              </linearGradient>
              <linearGradient id="benchmarkGrad" x1="0" y1="0" x2="0" y2="1">
                <stop offset="0%" stopColor="#10b981" stopOpacity="0.25" />
                <stop offset="100%" stopColor="#10b981" stopOpacity="0" />
              </linearGradient>
            </defs>
            
            {/* Grid lines */}
            <g stroke="#e5e7eb" strokeWidth="1" strokeDasharray="2,2">
              {[0, 0.25, 0.5, 0.75, 1].map(t => (
                <line
                  key={t}
                  x1={padding}
                  y1={padding + t * (height - padding * 2)}
                  x2={width - padding}
                  y2={padding + t * (height - padding * 2)}
                />
              ))}
            </g>
            
            {/* Portfolio area */}
            {portfolioPath && (
              <>
                <path
                  d={`${portfolioPath} L ${sx(portfolioSeries.length - 1)} ${sy(y0)} L ${sx(0)} ${sy(y0)} Z`}
                  fill="url(#portfolioGrad)"
                />
                <path
                  d={portfolioPath}
                  fill="none"
                  stroke="#3b82f6"
                  strokeWidth="2.5"
                />
              </>
            )}
            
            {/* Benchmark line */}
            {benchmarkPath && (
              <path
                d={benchmarkPath}
                fill="none"
                stroke="#10b981"
                strokeWidth="2.5"
                strokeDasharray="5,5"
              />
            )}
            
            {/* Interactive hover areas and points */}
            {portfolioSeries.map((point, i) => {
              const x = sx(i);
              const y = sy(point.value);
              const benchmarkValue = benchmarkSeries[i]?.value;
              
              return (
                <g key={i}>
                  {/* Invisible hover area */}
                  <rect
                    x={x - 10}
                    y={padding}
                    width={20}
                    height={height - padding * 2}
                    fill="transparent"
                    style={{ cursor: 'crosshair' }}
                    onMouseEnter={(e) => {
                      const rect = e.currentTarget.getBoundingClientRect();
                      const svgRect = e.currentTarget.ownerSVGElement.getBoundingClientRect();
                      const svgX = (rect.left + rect.width / 2 - svgRect.left) / (svgRect.width / width);
                      const svgY = (rect.top + rect.height / 2 - svgRect.top) / (svgRect.height / height);
                      
                      setHoveredPoint({
                        x: svgX * (svgRect.width / width),
                        y: svgY * (svgRect.height / height),
                        date: point.date,
                        portfolioValue: point.value,
                        benchmarkValue: benchmarkValue
                      });
                    }}
                  />
                  {/* Visible point on hover */}
                  {hoveredPoint && Math.abs(hoveredPoint.x - x) < 15 && (
                    <>
                      <circle
                        cx={x}
                        cy={y}
                        r={5}
                        fill="#3b82f6"
                        stroke="white"
                        strokeWidth={2}
                      />
                      {benchmarkValue !== undefined && (
                        <circle
                          cx={x}
                          cy={sy(benchmarkValue)}
                          r={5}
                          fill="#10b981"
                          stroke="white"
                          strokeWidth={2}
                        />
                      )}
                      {/* Vertical line */}
                      <line
                        x1={x}
                        y1={padding}
                        x2={x}
                        y2={height - padding}
                        stroke="#94a3b8"
                        strokeWidth="1"
                        strokeDasharray="3,3"
                      />
                    </>
                  )}
                </g>
              );
            })}
            
            {/* Y-axis labels */}
            <g className="text-xs fill-gray-600">
              {[0, 0.25, 0.5, 0.75, 1].map(t => {
                const val = y0 + (y1 - y0) * (1 - t);
                return (
                  <text
                    key={t}
                    x={padding - 10}
                    y={padding + t * (height - padding * 2) + 4}
                    textAnchor="end"
                  >
                    {formatYValue(val)}
                  </text>
                );
              })}
            </g>
            
            {/* X-axis date labels */}
            <g className="text-xs fill-gray-600">
              {(() => {
                const numLabels = Math.min(8, portfolioSeries.length);
                const step = Math.max(1, Math.floor(portfolioSeries.length / numLabels));
                const labels = [];
                
                for (let i = 0; i < portfolioSeries.length; i += step) {
                  if (i === portfolioSeries.length - 1 || labels.length < numLabels - 1) {
                    const point = portfolioSeries[i];
                    const x = sx(i);
                    const date = point.date;
                    const dateStr = date.toLocaleDateString('en-US', { month: 'short', day: 'numeric' });
                    
                    labels.push(
                      <text
                        key={i}
                        x={x}
                        y={height - padding + 20}
                        textAnchor="middle"
                      >
                        {dateStr}
                      </text>
                    );
                  }
                }
                // Always show last date
                if (portfolioSeries.length > 0) {
                  const lastPoint = portfolioSeries[portfolioSeries.length - 1];
                  const lastX = sx(portfolioSeries.length - 1);
                  const lastDateStr = lastPoint.date.toLocaleDateString('en-US', { month: 'short', day: 'numeric' });
                  
                  // Only add if not already added
                  if (labels.length === 0 || labels[labels.length - 1].key !== String(portfolioSeries.length - 1)) {
                    labels.push(
                      <text
                        key={portfolioSeries.length - 1}
                        x={lastX}
                        y={height - padding + 20}
                        textAnchor="middle"
                      >
                        {lastDateStr}
                      </text>
                    );
                  }
                }
                
                return labels;
              })()}
            </g>
          </svg>
          
          {/* Hover Tooltip */}
          {hoveredPoint && (
            <div
              className="absolute bg-gray-900 text-white px-3 py-2 rounded-lg shadow-lg text-sm pointer-events-none z-10"
              style={{
                left: `${(hoveredPoint.x / width) * 100}%`,
                top: `${(hoveredPoint.y / height) * 100}%`,
                transform: 'translate(-50%, -100%)',
                marginTop: '-10px'
              }}
            >
              <div className="font-semibold mb-1">
                {hoveredPoint.date.toLocaleDateString('en-US', { 
                  weekday: 'short',
                  month: 'short', 
                  day: 'numeric',
                  year: 'numeric'
                })}
              </div>
              <div className="flex items-center gap-2 mb-1">
                <div className="w-3 h-3 rounded-full bg-blue-600"></div>
                <span>Portfolio: {formatYValue(hoveredPoint.portfolioValue)}</span>
              </div>
              {hoveredPoint.benchmarkValue !== undefined && (
                <div className="flex items-center gap-2">
                  <div className="w-3 h-3 rounded-full bg-green-500"></div>
                  <span>Benchmark: {formatYValue(hoveredPoint.benchmarkValue)}</span>
                </div>
              )}
            </div>
          )}
        </div>
        
        {/* Legend */}
        <div className="flex items-center gap-6 mt-4 pt-4 border-t border-gray-200">
          <div className="flex items-center gap-2">
            <div className="w-4 h-0.5 bg-blue-600"></div>
            <span className="text-sm text-gray-600">Portfolio</span>
          </div>
          {benchmark !== 'none' && (
            <div className="flex items-center gap-2">
              <div className="w-4 h-0.5 bg-green-500 border-dashed border-t-2"></div>
              <span className="text-sm text-gray-600">Benchmark ({benchmark === 'custom' ? 'Custom' : benchmark})</span>
            </div>
          )}
        </div>
        
        {/* Timeframe buttons */}
        <div className="flex gap-2 mt-6 pt-4 border-t border-gray-200">
          {[1, 5, 30, 90, 180, 365].map(days => {
            const labels = { 1: '1D', 5: '5D', 30: '1M', 90: '3M', 180: '6M', 365: '1Y' };
            return (
              <button
                key={days}
                onClick={() => setTimeframe(days)}
                className={`px-4 py-2 rounded-md text-sm font-medium transition-colors ${
                  timeframe === days
                    ? 'bg-blue-600 text-white'
                    : 'bg-gray-100 text-gray-700 hover:bg-gray-200'
                }`}
              >
                {labels[days] || `${days}D`}
              </button>
            );
          })}
        </div>
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
            <div className="flex items-center gap-4">
              <div className="flex items-center gap-2 cursor-pointer">
                <div className="w-10 h-10 bg-blue-500 rounded-full"></div>
                <span className="font-medium">{username}</span>
              </div>
              <button
                onClick={handleLogout}
                className="p-2 hover:bg-gray-100 rounded-lg"
                title="Logout"
              >
                <LogOut className="w-5 h-5" />
              </button>
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
            {/* Performance Graph */}
            <PerformanceGraph />
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
