import React, { useState, useEffect, useMemo } from 'react';
import { Search, Menu, Bell, Moon, LogOut } from 'lucide-react';
import axios from 'axios';
import Login from './Login';

const API_URL = '/api';

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

  // Transaction filters
  const [symbolFilter, setSymbolFilter] = useState('all');
  const [typeFilter, setTypeFilter] = useState('all');
  const [dateFilter, setDateFilter] = useState('all');
  const [customDateRange, setCustomDateRange] = useState({ start: '', end: '' });
  const [groupFilter, setGroupFilter] = useState('all');
  const [transactionView, setTransactionView] = useState('stocks'); // 'stocks' | 'options'
  const [txPage, setTxPage] = useState(1);
  const TX_PAGE_SIZE = 15;

  // Performance graph controls
  const [yAxisType, setYAxisType] = useState('dollar');
  const [benchmark, setBenchmark] = useState('none');
  const [portfolioFilter, setPortfolioFilter] = useState('whole');
  const [benchmarkData, setBenchmarkData] = useState([]);
  const [timeframe, setTimeframe] = useState(30);
  const [availableStocks, setAvailableStocks] = useState([]);
  const [selectedStocks, setSelectedStocks] = useState(new Set());
  const [showStockFilter, setShowStockFilter] = useState(false);
  const [hoveredPoint, setHoveredPoint] = useState(null);

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
      const { data } = await axios.get(`${API_URL}/auth/status`, { withCredentials: true });
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
      const { data } = await axios.get(`${API_URL}/portfolio/stocks`, { withCredentials: true });
      if (data.success) {
        setAvailableStocks(data.data || []);
        setSelectedStocks(new Set(data.data.map(s => s.symbol)));
      }
    } catch (err) {
      console.error('Error fetching portfolio stocks:', err);
    }
  };

  const fetchPortfolioData = async () => {
    try {
      const { data } = await axios.get(`${API_URL}/portfolio/summary`, { withCredentials: true });
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
        params: { days: timeframe, daily: 'true', ...(symbols && { symbols }) },
        withCredentials: true
      });
      if (data.success && data.data) {
        const series = data.data.map(item => ({ date: new Date(item.date), value: Number(item.value) || 0 }));
        setGrowthData(series);
      }
    } catch (err) {
      console.error('Error fetching portfolio history:', err);
    }
  };

  const fetchBenchmarkData = async (symbol) => {
    if (!symbol || symbol === 'none') { setBenchmarkData([]); return; }
    try {
      const { data } = await axios.get(`${API_URL}/benchmark/history`, {
        params: { symbol, days: timeframe },
        withCredentials: true
      });
      if (data.success && data.data) {
        const series = data.data.map(item => ({ date: new Date(item.date), value: Number(item.value) || 0 }));
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
  }, [timeframe, benchmark, selectedStocks]);

  const fetchTransactions = async () => {
    try {
      const { data } = await axios.get(`${API_URL}/transactions`, { withCredentials: true });
      if (data.success) setTransactions(data.data);
    } catch (err) {
      console.error('Error fetching transactions:', err);
    }
  };

  const fetchWatchlist = async () => {
    try {
      const { data } = await axios.get(`${API_URL}/watchlist`, { withCredentials: true });
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

  // ── Order group map ──────────────────────────────────────────────────────────
  const orderGroupMap = useMemo(() => {
    const isFill = (action) =>
      action && (action.includes('BUY FILL') || action.includes('BUY PARTIAL_FILL'));

    const fills = transactions
      .map((tx, idx) => ({ tx, idx }))
      .filter(({ tx }) => isFill(tx.action));

    fills.sort((a, b) => {
      const symCmp = (a.tx.symbol || '').localeCompare(b.tx.symbol || '');
      if (symCmp !== 0) return symCmp;
      return new Date(a.tx.date) - new Date(b.tx.date);
    });

    const map = new Map();
    let counter = 1;
    let i = 0;

    while (i < fills.length) {
      const anchorSymbol = fills[i].tx.symbol || '';
      const group = counter++;

      // Rolling window: each item must be within 2 min of the PREVIOUS item
      // (not the anchor), so PARTIAL_FILLs chain correctly to their final FILL
      let lastTime = new Date(fills[i].tx.date).getTime();
      let j = i;

      while (j < fills.length) {
        const sym = fills[j].tx.symbol || '';
        const t = new Date(fills[j].tx.date).getTime();
        if (sym !== anchorSymbol || t - lastTime > 120_000) break;
        map.set(fills[j].idx, group);
        lastTime = t; // roll the window forward to this item's time
        j++;
      }

      i = j;
    }

    return map;
  }, [transactions]);

  const availableGroups = useMemo(() => {
    return [...new Set(orderGroupMap.values())].sort((a, b) => a - b);
  }, [orderGroupMap]);

  // Reset to page 1 whenever any filter or view changes
  useEffect(() => { setTxPage(1); }, [symbolFilter, typeFilter, dateFilter, groupFilter, transactionView, customDateRange]);

  // ── Filter + sort transactions ───────────────────────────────────────────────
  const getFilteredTransactions = () => {
    let filtered = transactions.map((tx, originalIdx) => ({ tx, originalIdx }));

    // Stock vs Options view filter
    filtered = filtered.filter(({ tx }) => {
      const type = tx.type || '';
      const isOption = type.includes('OPTIONEXERCISE') || type.includes('OPTRD');
      return transactionView === 'options' ? isOption : !isOption;
    });

    if (symbolFilter !== 'all') {
      filtered = filtered.filter(({ tx }) => tx.symbol === symbolFilter);
    }

    if (typeFilter !== 'all') {
      filtered = filtered.filter(({ tx }) => {
        if (typeFilter === 'buy') return tx.type === 'BUY';
        if (typeFilter === 'sell') return tx.type === 'SELL';
        if (typeFilter === 'fees') return tx.type === 'FEE';
        if (typeFilter === 'deposits') return tx.type === 'JNLC' || tx.action?.toLowerCase().includes('deposit');
        if (typeFilter === 'fill') return tx.action?.includes('FILL') && !tx.action?.includes('PARTIAL');
        if (typeFilter === 'partial') return tx.action?.includes('PARTIAL_FILL');
        return true;
      });
    }

    if (dateFilter !== 'all') {
      const now = new Date();
      const today = new Date(now.getFullYear(), now.getMonth(), now.getDate());
      filtered = filtered.filter(({ tx }) => {
        const txDate = tx.date ? new Date(tx.date) : new Date();
        if (dateFilter === 'today') return txDate >= today;
        if (dateFilter === 'week') {
          const weekAgo = new Date(today); weekAgo.setDate(weekAgo.getDate() - 7);
          return txDate >= weekAgo;
        }
        if (dateFilter === 'month') {
          const monthAgo = new Date(today); monthAgo.setMonth(monthAgo.getMonth() - 1);
          return txDate >= monthAgo;
        }
        if (dateFilter === 'custom' && customDateRange.start && customDateRange.end) {
          const startDate = new Date(customDateRange.start);
          const endDate = new Date(customDateRange.end);
          endDate.setHours(23, 59, 59, 999);
          return txDate >= startDate && txDate <= endDate;
        }
        return true;
      });
    }

    if (groupFilter !== 'all') {
      const targetGroup = Number(groupFilter);
      filtered = filtered.filter(({ originalIdx }) => orderGroupMap.get(originalIdx) === targetGroup);
    }

    filtered.sort((a, b) => {
      const ga = orderGroupMap.get(a.originalIdx) ?? Infinity;
      const gb = orderGroupMap.get(b.originalIdx) ?? Infinity;
      if (ga !== gb) return ga - gb;
      return new Date(a.tx.date) - new Date(b.tx.date);
    });

    return filtered;
  };

  const getUniqueSymbols = () => {
    const symbols = new Set();
    transactions.forEach(tx => { if (tx.symbol && tx.symbol !== 'N/A') symbols.add(tx.symbol); });
    return Array.from(symbols).sort();
  };

  // ── Early-return states ──────────────────────────────────────────────────────
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

  if (!isAuthenticated) return <Login onLogin={handleLogin} />;

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
          <button onClick={() => window.location.reload()} className="mt-4 px-4 py-2 bg-red-600 text-white rounded-lg hover:bg-red-700">
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

  const bestPerformer = holdings.length ? holdings.reduce((max, h) => (h.change > max.change ? h : max), holdings[0]) : null;
  const worstPerformer = holdings.length ? holdings.reduce((min, h) => (h.change < min.change ? h : min), holdings[0]) : null;

  const calculateReturns = (data) => {
    if (!data || data.length === 0) return [];
    const firstValue = data[0].value;
    if (!firstValue || firstValue === 0) return data.map(d => ({ ...d, value: 0 }));
    return data.map(d => ({ ...d, value: ((d.value - firstValue) / firstValue) * 100 }));
  };

  const normalizeBenchmark = (portfolioData, benchmarkData) => {
    if (!portfolioData?.length || !benchmarkData?.length) return benchmarkData;
    const portfolioFirst = portfolioData[0].value;
    const benchmarkFirst = benchmarkData[0].value;
    if (!portfolioFirst || !benchmarkFirst || benchmarkFirst === 0) return benchmarkData;
    const scale = portfolioFirst / benchmarkFirst;
    return benchmarkData.map(d => ({ ...d, value: d.value * scale }));
  };

  const calculatePerformanceMetrics = (portfolioSeries, benchmarkSeries) => {
    if (!portfolioSeries || portfolioSeries.length < 2) {
      return { sharpeRatio: 0, maxDrawdown: 0, volatility: 0, beta: 0, alpha: 0, winRate: 0 };
    }

    const portfolioReturns = [];
    for (let i = 1; i < portfolioSeries.length; i++) {
      const prev = portfolioSeries[i - 1].value;
      const curr = portfolioSeries[i].value;
      if (prev > 0) portfolioReturns.push((curr - prev) / prev);
    }

    const benchmarkReturns = [];
    if (benchmarkSeries && benchmarkSeries.length > 1) {
      for (let i = 1; i < benchmarkSeries.length; i++) {
        const prev = benchmarkSeries[i - 1].value;
        const curr = benchmarkSeries[i].value;
        if (prev > 0) benchmarkReturns.push((curr - prev) / prev);
      }
    }

    const avgReturn = portfolioReturns.reduce((a, b) => a + b, 0) / portfolioReturns.length;
    const variance = portfolioReturns.reduce((sum, r) => sum + Math.pow(r - avgReturn, 2), 0) / portfolioReturns.length;
    const stdDev = Math.sqrt(variance);
    const sharpeRatio = stdDev > 0 ? (avgReturn / stdDev) * Math.sqrt(252) : 0;

    let maxDrawdown = 0;
    let peak = portfolioSeries[0].value;
    for (let i = 1; i < portfolioSeries.length; i++) {
      const value = portfolioSeries[i].value;
      if (value > peak) peak = value;
      const drawdown = (peak - value) / peak;
      if (drawdown > maxDrawdown) maxDrawdown = drawdown;
    }

    const volatility = stdDev * Math.sqrt(252) * 100;

    let beta = 0;
    if (benchmarkReturns.length === portfolioReturns.length && benchmarkReturns.length > 1) {
      const benchmarkMean = benchmarkReturns.reduce((a, b) => a + b, 0) / benchmarkReturns.length;
      let covariance = 0, benchmarkVariance = 0;
      for (let i = 0; i < portfolioReturns.length; i++) {
        covariance += (portfolioReturns[i] - avgReturn) * (benchmarkReturns[i] - benchmarkMean);
        benchmarkVariance += Math.pow(benchmarkReturns[i] - benchmarkMean, 2);
      }
      covariance /= portfolioReturns.length;
      benchmarkVariance /= portfolioReturns.length;
      beta = benchmarkVariance > 0 ? covariance / benchmarkVariance : 0;
    }

    let alpha = 0;
    if (benchmarkReturns.length === portfolioReturns.length && benchmarkReturns.length > 1) {
      const portfolioTotalReturn = (portfolioSeries[portfolioSeries.length - 1].value - portfolioSeries[0].value) / portfolioSeries[0].value;
      const benchmarkTotalReturn = (benchmarkSeries[benchmarkSeries.length - 1].value - benchmarkSeries[0].value) / benchmarkSeries[0].value;
      const days = portfolioSeries.length;
      alpha = (Math.pow(1 + portfolioTotalReturn, 252 / days) - 1 - (Math.pow(1 + benchmarkTotalReturn, 252 / days) - 1)) * 100;
    }

    const winRate = portfolioReturns.length > 0 ? (portfolioReturns.filter(r => r > 0).length / portfolioReturns.length) * 100 : 0;

    return {
      sharpeRatio: sharpeRatio || 0,
      maxDrawdown: maxDrawdown * 100 || 0,
      volatility: volatility || 0,
      beta: beta || 0,
      alpha: alpha || 0,
      winRate: winRate || 0
    };
  };

  const PerformanceGraph = () => {
    const height = 400;
    const width = 800;
    const padding = 60;

    let portfolioPoints = growthData || [];
    if (yAxisType === 'return') portfolioPoints = calculateReturns(portfolioPoints);

    let benchmarkPoints = benchmarkData || [];
    if (benchmarkPoints.length > 0) {
      benchmarkPoints = yAxisType === 'return'
        ? calculateReturns(benchmarkPoints)
        : normalizeBenchmark(portfolioPoints, benchmarkPoints);
    }

    const allDates = [...new Set([
      ...portfolioPoints.map(p => p.date.getTime()),
      ...benchmarkPoints.map(p => p.date.getTime())
    ])].sort((a, b) => a - b);

    if (allDates.length === 0) {
      return <div className="bg-white rounded-2xl p-6 shadow-sm"><div className="text-center py-12 text-gray-500">No data available</div></div>;
    }

    const getValueAtDate = (data, date) => {
      const sorted = [...data].sort((a, b) => a.date - b.date);
      for (let i = 0; i < sorted.length; i++) {
        if (sorted[i].date.getTime() >= date) {
          if (i === 0) return sorted[0].value;
          const prev = sorted[i - 1], curr = sorted[i];
          const ratio = (date - prev.date.getTime()) / (curr.date.getTime() - prev.date.getTime());
          return prev.value + (curr.value - prev.value) * ratio;
        }
      }
      return sorted[sorted.length - 1]?.value || 0;
    };

    const portfolioSeries = allDates.map(date => ({ date: new Date(date), value: getValueAtDate(portfolioPoints, date) }));
    const benchmarkSeries = benchmarkPoints.length > 0
      ? allDates.map(date => ({ date: new Date(date), value: getValueAtDate(benchmarkPoints, date) }))
      : [];

    const allValues = [
      ...portfolioSeries.map(p => p.value),
      ...benchmarkSeries.map(p => p.value)
    ].filter(v => !isNaN(v) && isFinite(v));

    if (allValues.length === 0) {
      return <div className="bg-white rounded-2xl p-6 shadow-sm"><div className="text-center py-12 text-gray-500">No valid data points</div></div>;
    }

    const yMin = Math.min(...allValues);
    const yMax = Math.max(...allValues);
    const yPad = (yMax - yMin) * 0.1 || 1;
    const y0 = yMin - yPad, y1 = yMax + yPad;

    const sx = (i) => padding + (i / (allDates.length - 1 || 1)) * (width - padding * 2);
    const sy = (y) => padding + (1 - (y - y0) / (y1 - y0 || 1)) * (height - padding * 2);

    const portfolioPath = portfolioSeries.map((p, i) => `${i === 0 ? 'M' : 'L'} ${sx(i)} ${sy(p.value)}`).join(' ');
    const benchmarkPath = benchmarkSeries.length > 0
      ? benchmarkSeries.map((p, i) => `${i === 0 ? 'M' : 'L'} ${sx(i)} ${sy(p.value)}`).join(' ')
      : '';

    const firstPortfolio = portfolioSeries[0]?.value ?? 0;
    const lastPortfolio = portfolioSeries[portfolioSeries.length - 1]?.value ?? 0;
    const portfolioReturn = firstPortfolio ? ((lastPortfolio - firstPortfolio) / Math.abs(firstPortfolio)) * 100 : 0;

    const metrics = calculatePerformanceMetrics(
      (growthData || []).map(p => ({ date: typeof p.date === 'string' ? new Date(p.date) : p.date, value: p.value })),
      (benchmarkData || []).map(p => ({ date: typeof p.date === 'string' ? new Date(p.date) : p.date, value: p.value }))
    );

    const formatYValue = (val) => yAxisType === 'return'
      ? `${val >= 0 ? '+' : ''}${val.toFixed(2)}%`
      : `$${val.toLocaleString(undefined, { maximumFractionDigits: 0 })}`;

    return (
      <div className="bg-white rounded-2xl p-6 shadow-sm">
        <div className="mb-6">
          <h2 className="text-2xl font-bold text-gray-900 mb-2">Portfolio Performance</h2>
          <div className="text-3xl font-bold text-gray-900 mb-1">
            {yAxisType === 'return'
              ? `${portfolioReturn >= 0 ? '+' : ''}${portfolioReturn.toFixed(2)}%`
              : `$${lastPortfolio.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`}
          </div>
          <div className={`text-sm ${portfolioReturn >= 0 ? 'text-green-600' : 'text-red-600'}`}>
            {portfolioReturn >= 0 ? '+' : ''}{portfolioReturn.toFixed(2)}% ({portfolioReturn >= 0 ? '+' : ''}{(lastPortfolio - firstPortfolio).toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })}) Today
          </div>
          <div className="text-xs text-gray-500 mt-1">
            Closed: {new Date().toLocaleString('en-US', { month: 'short', day: 'numeric', hour: 'numeric', minute: 'numeric', timeZoneName: 'short' })}
          </div>
        </div>

        <div className="border-t border-gray-200 pt-4 mb-4"></div>

        <div className="mb-6 space-y-4">
          <div className="flex flex-wrap gap-4 items-center">
            <div className="flex items-center gap-2">
              <label className="text-sm font-medium text-gray-700">Portfolio:</label>
              <select value={portfolioFilter} onChange={(e) => setPortfolioFilter(e.target.value)}
                className="px-3 py-1.5 border border-gray-300 rounded-md text-sm focus:outline-none focus:ring-2 focus:ring-blue-500">
                <option value="whole">Whole Portfolio</option>
                <option value="risk">Risk Portfolio Only</option>
              </select>
            </div>
            <div className="flex items-center gap-2">
              <label className="text-sm font-medium text-gray-700">Y-axis:</label>
              <select value={yAxisType} onChange={(e) => setYAxisType(e.target.value)}
                className="px-3 py-1.5 border border-gray-300 rounded-md text-sm focus:outline-none focus:ring-2 focus:ring-blue-500">
                <option value="dollar">Dollar Value</option>
                <option value="return">Return (%)</option>
              </select>
            </div>
            <div className="flex items-center gap-2">
              <label className="text-sm font-medium text-gray-700">Benchmark:</label>
              <select value={benchmark} onChange={(e) => setBenchmark(e.target.value)}
                className="px-3 py-1.5 border border-gray-300 rounded-md text-sm focus:outline-none focus:ring-2 focus:ring-blue-500">
                <option value="none">None</option>
                <option value="SPY">Market Index (SPY)</option>
                <option value="custom">Custom Portfolio</option>
              </select>
            </div>
            <button onClick={() => setShowStockFilter(!showStockFilter)}
              className="px-3 py-1.5 border border-gray-300 rounded-md text-sm hover:bg-gray-50 focus:outline-none focus:ring-2 focus:ring-blue-500">
              {showStockFilter ? 'Hide' : 'Select Stocks'} ({selectedStocks.size}/{availableStocks.length})
            </button>
          </div>

          {showStockFilter && (
            <div className="bg-gray-50 rounded-lg p-4 border border-gray-200">
              <div className="flex items-center justify-between mb-3">
                <label className="text-sm font-medium text-gray-700">Select Stocks to Include:</label>
                <div className="flex gap-2">
                  <button onClick={() => setSelectedStocks(new Set(availableStocks.map(s => s.symbol)))}
                    className="text-xs px-2 py-1 text-blue-600 hover:text-blue-800">Select All</button>
                  <button onClick={() => setSelectedStocks(new Set())}
                    className="text-xs px-2 py-1 text-blue-600 hover:text-blue-800">Clear All</button>
                </div>
              </div>
              <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-4 gap-3 max-h-48 overflow-y-auto">
                {availableStocks.map((stock) => (
                  <label key={stock.symbol} className="flex items-center gap-2 cursor-pointer hover:bg-white p-2 rounded">
                    <input type="checkbox" checked={selectedStocks.has(stock.symbol)}
                      onChange={(e) => {
                        const newSelected = new Set(selectedStocks);
                        e.target.checked ? newSelected.add(stock.symbol) : newSelected.delete(stock.symbol);
                        setSelectedStocks(newSelected);
                      }}
                      className="w-4 h-4 text-blue-600 border-gray-300 rounded focus:ring-blue-500" />
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

        <div className="bg-gray-50 rounded-lg p-4 relative">
          <svg viewBox={`0 0 ${width} ${height}`} className="w-full" style={{ minHeight: '400px' }}
            onMouseLeave={() => setHoveredPoint(null)}>
            <defs>
              <linearGradient id="portfolioGrad" x1="0" y1="0" x2="0" y2="1">
                <stop offset="0%" stopColor="#3b82f6" stopOpacity="0.25" />
                <stop offset="100%" stopColor="#3b82f6" stopOpacity="0" />
              </linearGradient>
            </defs>
            <g stroke="#e5e7eb" strokeWidth="1" strokeDasharray="2,2">
              {[0, 0.25, 0.5, 0.75, 1].map(t => (
                <line key={t} x1={padding} y1={padding + t * (height - padding * 2)}
                  x2={width - padding} y2={padding + t * (height - padding * 2)} />
              ))}
            </g>
            {portfolioPath && (
              <>
                <path d={`${portfolioPath} L ${sx(portfolioSeries.length - 1)} ${sy(y0)} L ${sx(0)} ${sy(y0)} Z`} fill="url(#portfolioGrad)" />
                <path d={portfolioPath} fill="none" stroke="#3b82f6" strokeWidth="2.5" />
              </>
            )}
            {benchmarkPath && <path d={benchmarkPath} fill="none" stroke="#10b981" strokeWidth="2.5" strokeDasharray="5,5" />}
            {portfolioSeries.map((point, i) => {
              const x = sx(i), y = sy(point.value);
              const benchmarkValue = benchmarkSeries[i]?.value;
              return (
                <g key={i}>
                  <rect x={x - 10} y={padding} width={20} height={height - padding * 2} fill="transparent" style={{ cursor: 'crosshair' }}
                    onMouseEnter={(e) => {
                      const rect = e.currentTarget.getBoundingClientRect();
                      const svgRect = e.currentTarget.ownerSVGElement.getBoundingClientRect();
                      const svgX = (rect.left + rect.width / 2 - svgRect.left) / (svgRect.width / width);
                      const svgY = (rect.top + rect.height / 2 - svgRect.top) / (svgRect.height / height);
                      setHoveredPoint({ x: svgX * (svgRect.width / width), y: svgY * (svgRect.height / height), date: point.date, portfolioValue: point.value, benchmarkValue });
                    }} />
                  {hoveredPoint && Math.abs(hoveredPoint.x - x) < 15 && (
                    <>
                      <circle cx={x} cy={y} r={5} fill="#3b82f6" stroke="white" strokeWidth={2} />
                      {benchmarkValue !== undefined && <circle cx={x} cy={sy(benchmarkValue)} r={5} fill="#10b981" stroke="white" strokeWidth={2} />}
                      <line x1={x} y1={padding} x2={x} y2={height - padding} stroke="#94a3b8" strokeWidth="1" strokeDasharray="3,3" />
                    </>
                  )}
                </g>
              );
            })}
            <g className="text-xs fill-gray-600">
              {[0, 0.25, 0.5, 0.75, 1].map(t => {
                const val = y0 + (y1 - y0) * (1 - t);
                return <text key={t} x={padding - 10} y={padding + t * (height - padding * 2) + 4} textAnchor="end">{formatYValue(val)}</text>;
              })}
            </g>
            <g className="text-xs fill-gray-600">
              {(() => {
                if (portfolioSeries.length === 0) return [];
                const numLabels = Math.min(8, portfolioSeries.length);
                const firstDate = portfolioSeries[0].date.getTime();
                const lastDate = portfolioSeries[portfolioSeries.length - 1].date.getTime();
                const dateRange = lastDate - firstDate;
                const labels = [], labelIndices = new Set();
                for (let i = 0; i < numLabels; i++) {
                  const targetTime = firstDate + (dateRange * i / (numLabels - 1));
                  let closestIdx = 0, minDiff = Math.abs(portfolioSeries[0].date.getTime() - targetTime);
                  for (let j = 1; j < portfolioSeries.length; j++) {
                    const diff = Math.abs(portfolioSeries[j].date.getTime() - targetTime);
                    if (diff < minDiff) { minDiff = diff; closestIdx = j; }
                  }
                  if (!labelIndices.has(closestIdx)) {
                    labelIndices.add(closestIdx);
                    const point = portfolioSeries[closestIdx];
                    labels.push(
                      <text key={closestIdx} x={sx(closestIdx)} y={height - padding + 20} textAnchor="middle">
                        {point.date.toLocaleDateString('en-US', { month: 'short', day: 'numeric' })}
                      </text>
                    );
                  }
                }
                return labels;
              })()}
            </g>
          </svg>

          {hoveredPoint && (
            <div className="absolute bg-gray-900 text-white px-3 py-2 rounded-lg shadow-lg text-sm pointer-events-none z-10"
              style={{ left: `${(hoveredPoint.x / width) * 100}%`, top: `${(hoveredPoint.y / height) * 100}%`, transform: 'translate(-50%, -100%)', marginTop: '-10px' }}>
              <div className="font-semibold mb-1">
                {hoveredPoint.date.toLocaleDateString('en-US', { weekday: 'short', month: 'short', day: 'numeric', year: 'numeric' })}
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

        <div className="flex gap-2 mt-6 pt-4 border-t border-gray-200">
          {[1, 5, 30, 90, 180, 365].map(days => {
            const labels = { 1: '1D', 5: '5D', 30: '1M', 90: '3M', 180: '6M', 365: '1Y' };
            return (
              <button key={days} onClick={() => setTimeframe(days)}
                className={`px-4 py-2 rounded-md text-sm font-medium transition-colors ${timeframe === days ? 'bg-blue-600 text-white' : 'bg-gray-100 text-gray-700 hover:bg-gray-200'}`}>
                {labels[days] || `${days}D`}
              </button>
            );
          })}
        </div>

        <div className="mt-6 pt-6 border-t border-gray-200">
          <h3 className="text-lg font-semibold text-gray-900 mb-4">Performance Metrics</h3>
          <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-6 gap-4">
            <div className="bg-gradient-to-br from-blue-50 to-blue-100 rounded-lg p-4 border border-blue-200">
              <div className="text-xs text-blue-700 font-medium mb-1">Sharpe Ratio</div>
              <div className="text-2xl font-bold text-blue-900">{metrics.sharpeRatio.toFixed(2)}</div>
              <div className="text-xs text-blue-600 mt-1">{metrics.sharpeRatio > 1 ? 'Excellent' : metrics.sharpeRatio > 0.5 ? 'Good' : metrics.sharpeRatio > 0 ? 'Fair' : 'Poor'}</div>
            </div>
            <div className="bg-gradient-to-br from-red-50 to-red-100 rounded-lg p-4 border border-red-200">
              <div className="text-xs text-red-700 font-medium mb-1">Max Drawdown</div>
              <div className="text-2xl font-bold text-red-900">{metrics.maxDrawdown.toFixed(2)}%</div>
              <div className="text-xs text-red-600 mt-1">{metrics.maxDrawdown < 10 ? 'Low Risk' : metrics.maxDrawdown < 20 ? 'Moderate' : 'High Risk'}</div>
            </div>
            <div className="bg-gradient-to-br from-purple-50 to-purple-100 rounded-lg p-4 border border-purple-200">
              <div className="text-xs text-purple-700 font-medium mb-1">Volatility</div>
              <div className="text-2xl font-bold text-purple-900">{metrics.volatility.toFixed(2)}%</div>
              <div className="text-xs text-purple-600 mt-1">Annualized</div>
            </div>
            <div className="bg-gradient-to-br from-green-50 to-green-100 rounded-lg p-4 border border-green-200">
              <div className="text-xs text-green-700 font-medium mb-1">Beta</div>
              <div className="text-2xl font-bold text-green-900">{metrics.beta.toFixed(2)}</div>
              <div className="text-xs text-green-600 mt-1">{metrics.beta > 1 ? 'More Volatile' : metrics.beta < 1 ? 'Less Volatile' : 'Market Match'}</div>
            </div>
            <div className="bg-gradient-to-br from-orange-50 to-orange-100 rounded-lg p-4 border border-orange-200">
              <div className="text-xs text-orange-700 font-medium mb-1">Alpha</div>
              <div className={`text-2xl font-bold ${metrics.alpha >= 0 ? 'text-orange-900' : 'text-orange-700'}`}>
                {metrics.alpha >= 0 ? '+' : ''}{metrics.alpha.toFixed(2)}%
              </div>
              <div className="text-xs text-orange-600 mt-1">{benchmark !== 'none' ? 'vs Benchmark' : 'N/A'}</div>
            </div>
            <div className="bg-gradient-to-br from-indigo-50 to-indigo-100 rounded-lg p-4 border border-indigo-200">
              <div className="text-xs text-indigo-700 font-medium mb-1">Win Rate</div>
              <div className="text-2xl font-bold text-indigo-900">{metrics.winRate.toFixed(1)}%</div>
              <div className="text-xs text-indigo-600 mt-1">Profitable Periods</div>
            </div>
          </div>
        </div>
      </div>
    );
  };

  return (
    <div className="min-h-screen bg-gray-50">
      <header className="bg-white border-b border-gray-200 px-6 py-4">
        <div className="flex items-center justify-between max-w-7xl mx-auto">
          <div className="flex items-center gap-4">
            <button className="p-2 hover:bg-gray-100 rounded-lg"><Menu className="w-5 h-5" /></button>
            <div className="relative flex-1 max-w-md">
              <Search className="absolute left-3 top-1/2 transform -translate-y-1/2 w-5 h-5 text-gray-400" />
              <input type="text" placeholder="Search or type command..."
                className="w-full pl-10 pr-20 py-2 border border-gray-200 rounded-lg focus:outline-none focus:ring-2 focus:ring-blue-500" />
              <kbd className="absolute right-3 top-1/2 transform -translate-y-1/2 px-2 py-1 text-xs bg-gray-100 rounded">⌘ K</kbd>
            </div>
          </div>
          <div className="flex items-center gap-4">
            <button className="p-2 hover:bg-gray-100 rounded-lg"><Moon className="w-5 h-5" /></button>
            <button className="p-2 hover:bg-gray-100 rounded-lg relative">
              <Bell className="w-5 h-5" />
              <span className="absolute top-1 right-1 w-2 h-2 bg-orange-500 rounded-full"></span>
            </button>
            <div className="flex items-center gap-4">
              <div className="flex items-center gap-2 cursor-pointer">
                <div className="w-10 h-10 bg-blue-500 rounded-full"></div>
                <span className="font-medium">{username}</span>
              </div>
              <button onClick={handleLogout} className="p-2 hover:bg-gray-100 rounded-lg" title="Logout">
                <LogOut className="w-5 h-5" />
              </button>
            </div>
          </div>
        </div>
      </header>

      <main className="max-w-7xl mx-auto px-6 py-8">
        {watchlistQuotes.length > 0 && (
          <section className="bg-white rounded-xl shadow-sm mb-6 overflow-hidden">
            <div className="flex items-center justify-between px-4 pt-3">
              <h3 className="text-sm font-semibold text-gray-700">Watchlist</h3>
            </div>
            <div className="relative w-full h-[84px]">
              <div className="absolute inset-0 flex transition-transform duration-500 ease-out"
                style={{ width: `${watchlistQuotes.length * 240}px`, transform: `translateX(-${watchlistIndex * 240}px)` }}>
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
                          <div className={`text-xs ${up ? 'text-green-600' : 'text-red-600'}`}>
                            {up ? '+' : ''}{Number(q.changePercent || 0).toFixed(2)}%
                          </div>
                        </div>
                      </div>
                    </div>
                  );
                })}
              </div>
            </div>
          </section>
        )}

        <section className="bg-gradient-to-r from-blue-600 to-blue-800 rounded-2xl p-8 text-white mb-6">
          <h1 className="text-2xl font-bold mb-4">Portfolio Overview</h1>
          <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
            <div>
              <p className="text-blue-200 text-sm mb-1">Total Value</p>
              <p className="text-3xl font-bold">${totalValue.toLocaleString(undefined, { minimumFractionDigits: 2 })}</p>
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
          <div className="lg:col-span-2 space-y-6">
            <PerformanceGraph />

            <section className="bg-white rounded-2xl p-6 shadow-sm">
              <h2 className="text-2xl font-bold text-gray-900 mb-6">Your Holdings</h2>
              {holdings.length > 0 ? (
                <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                  {holdings.map((holding, idx) => {
                    const gainLoss = holding.marketValue - holding.costBasis;
                    const gainLossPercent = holding.costBasis > 0 ? (gainLoss / holding.costBasis) * 100 : 0;
                    const avgPrice = holding.costBasis / holding.quantity || 0;
                    return (
                      <div key={idx} className="bg-gradient-to-br from-white to-gray-50 rounded-xl p-6 border border-gray-200 hover:shadow-lg transition-shadow">
                        <div className="flex items-start justify-between mb-4">
                          <div className="flex-1">
                            <div className="flex items-center gap-2 mb-1">
                              <div className="font-bold text-gray-900 text-xl">{safeText(holding.symbol)}</div>
                              <div className={`px-2 py-0.5 rounded text-xs font-medium ${holding.change > 0 ? 'bg-green-100 text-green-700' : 'bg-red-100 text-red-700'}`}>
                                {holding.change > 0 ? '+' : ''}{holding.change.toFixed(2)}%
                              </div>
                            </div>
                            <div className="text-sm text-gray-600 mb-2">{safeText(holding.name)}</div>
                            <div className="text-xs text-gray-500">{holding.quantity.toLocaleString()} shares</div>
                          </div>
                          <div className="text-right ml-4">
                            <div className="font-bold text-gray-900 text-lg">${holding.price.toFixed(2)}</div>
                            <div className={`text-sm flex items-center gap-1 justify-end mt-1 ${holding.change > 0 ? 'text-green-600' : 'text-red-600'}`}>
                              <span>{holding.change > 0 ? '↑' : '↓'}</span>
                              {Math.abs(holding.change).toFixed(2)}%
                            </div>
                          </div>
                        </div>
                        <div className="border-t border-gray-200 pt-4 mt-4 space-y-2">
                          <div className="grid grid-cols-2 gap-4">
                            <div>
                              <div className="text-xs text-gray-500 mb-1">Market Value</div>
                              <div className="font-semibold text-gray-900">${holding.marketValue.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })}</div>
                            </div>
                            <div>
                              <div className="text-xs text-gray-500 mb-1">Cost Basis</div>
                              <div className="font-semibold text-gray-900">${holding.costBasis.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })}</div>
                            </div>
                          </div>
                          <div className="grid grid-cols-2 gap-4 pt-2 border-t border-gray-100">
                            <div>
                              <div className="text-xs text-gray-500 mb-1">Avg Price</div>
                              <div className="font-medium text-gray-700">${avgPrice.toFixed(2)}</div>
                            </div>
                            <div>
                              <div className="text-xs text-gray-500 mb-1">Gain/Loss</div>
                              <div className={`font-semibold ${gainLoss >= 0 ? 'text-green-600' : 'text-red-600'}`}>
                                {gainLoss >= 0 ? '+' : ''}${gainLoss.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })}
                              </div>
                              <div className={`text-xs ${gainLossPercent >= 0 ? 'text-green-600' : 'text-red-600'}`}>
                                ({gainLossPercent >= 0 ? '+' : ''}{gainLossPercent.toFixed(2)}%)
                              </div>
                            </div>
                          </div>
                        </div>
                      </div>
                    );
                  })}
                </div>
              ) : (
                <div className="text-center py-12 text-gray-500">No holdings found in your portfolio</div>
              )}
            </section>

            {/* ── Recent Transactions ─────────────────────────────────────────── */}
            <section className="bg-white rounded-2xl p-6 shadow-sm">
              {/* Header row: title left, Stocks/Options toggle right */}
              <div className="flex items-center justify-between mb-6">
                <h2 className="text-2xl font-bold text-gray-900">Recent Transactions</h2>

                {/* Stocks / Options segmented pill */}
                <div className="flex rounded-lg border border-gray-200 overflow-hidden text-sm font-medium shadow-sm">
                  <button
                    onClick={() => setTransactionView('stocks')}
                    className={`px-5 py-2 transition-colors ${transactionView === 'stocks'
                      ? 'bg-blue-600 text-white'
                      : 'bg-white text-gray-500 hover:bg-gray-50'
                      }`}
                  >
                    Stocks
                  </button>
                  <button
                    onClick={() => setTransactionView('options')}
                    className={`px-5 py-2 border-l border-gray-200 transition-colors ${transactionView === 'options'
                      ? 'bg-blue-600 text-white'
                      : 'bg-white text-gray-500 hover:bg-gray-50'
                      }`}
                  >
                    Options
                  </button>
                </div>
              </div>

              <div className="mb-6 space-y-4">
                <div className="flex flex-wrap gap-4">
                  {/* Symbol filter */}
                  <div className="flex-1 min-w-[160px]">
                    <label className="block text-sm font-medium text-gray-700 mb-2">Symbol</label>
                    <select value={symbolFilter} onChange={(e) => setSymbolFilter(e.target.value)}
                      className="w-full px-3 py-2 border border-gray-300 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-blue-500">
                      <option value="all">All Symbols</option>
                      {getUniqueSymbols().map(symbol => <option key={symbol} value={symbol}>{symbol}</option>)}
                    </select>
                  </div>

                  {/* Type filter */}
                  <div className="flex-1 min-w-[160px]">
                    <label className="block text-sm font-medium text-gray-700 mb-2">Type</label>
                    <select value={typeFilter} onChange={(e) => setTypeFilter(e.target.value)}
                      className="w-full px-3 py-2 border border-gray-300 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-blue-500">
                      <option value="all">All Types</option>
                      <option value="buy">Buy Orders</option>
                      <option value="sell">Sell Orders</option>
                      <option value="fill">Fills</option>
                      <option value="partial">Partial Fills</option>
                      <option value="fees">Fees Only</option>
                      <option value="deposits">Deposits/Withdrawals</option>
                    </select>
                  </div>

                  {/* Date filter */}
                  <div className="flex-1 min-w-[160px]">
                    <label className="block text-sm font-medium text-gray-700 mb-2">Date Range</label>
                    <select value={dateFilter} onChange={(e) => setDateFilter(e.target.value)}
                      className="w-full px-3 py-2 border border-gray-300 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-blue-500">
                      <option value="all">All Time</option>
                      <option value="today">Today</option>
                      <option value="week">Last 7 Days</option>
                      <option value="month">Last 30 Days</option>
                      <option value="custom">Custom Range</option>
                    </select>
                  </div>

                  {/* Order Group filter */}
                  <div className="flex-1 min-w-[160px]">
                    <label className="block text-sm font-medium text-gray-700 mb-2">Order Group</label>
                    <select value={groupFilter} onChange={(e) => setGroupFilter(e.target.value)}
                      className="w-full px-3 py-2 border border-gray-300 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-violet-500">
                      <option value="all">All Groups</option>
                      {availableGroups.map(g => (
                        <option key={g} value={g}>Group #{g}</option>
                      ))}
                    </select>
                  </div>
                </div>

                {dateFilter === 'custom' && (
                  <div className="flex gap-4 items-end">
                    <div className="flex-1">
                      <label className="block text-sm font-medium text-gray-700 mb-2">Start Date</label>
                      <input type="date" value={customDateRange.start}
                        onChange={(e) => setCustomDateRange({ ...customDateRange, start: e.target.value })}
                        className="w-full px-3 py-2 border border-gray-300 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-blue-500" />
                    </div>
                    <div className="flex-1">
                      <label className="block text-sm font-medium text-gray-700 mb-2">End Date</label>
                      <input type="date" value={customDateRange.end}
                        onChange={(e) => setCustomDateRange({ ...customDateRange, end: e.target.value })}
                        className="w-full px-3 py-2 border border-gray-300 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-blue-500" />
                    </div>
                  </div>
                )}

                {(symbolFilter !== 'all' || typeFilter !== 'all' || dateFilter !== 'all' || groupFilter !== 'all') && (
                  <div className="flex items-center justify-between pt-2 border-t border-gray-200">
                    <div className="flex flex-wrap items-center gap-2 text-sm text-gray-600">
                      <span>Active filters:</span>
                      {symbolFilter !== 'all' && <span className="px-2 py-1 bg-blue-100 text-blue-700 rounded-md">Symbol: {symbolFilter}</span>}
                      {typeFilter !== 'all' && <span className="px-2 py-1 bg-blue-100 text-blue-700 rounded-md">Type: {typeFilter}</span>}
                      {dateFilter !== 'all' && <span className="px-2 py-1 bg-blue-100 text-blue-700 rounded-md">Date: {dateFilter === 'custom' ? 'Custom' : dateFilter}</span>}
                      {groupFilter !== 'all' && <span className="px-2 py-1 bg-violet-100 text-violet-700 rounded-md">Group: #{groupFilter}</span>}
                    </div>
                    <button
                      onClick={() => {
                        setSymbolFilter('all');
                        setTypeFilter('all');
                        setDateFilter('all');
                        setCustomDateRange({ start: '', end: '' });
                        setGroupFilter('all');
                        setTransactionView('stocks');
                      }}
                      className="text-sm text-blue-600 hover:text-blue-800 font-medium">
                      Clear All Filters
                    </button>
                  </div>
                )}
              </div>

              {(() => {
                const filteredRows = getFilteredTransactions();
                const totalPages = Math.max(1, Math.ceil(filteredRows.length / TX_PAGE_SIZE));
                const safePage = Math.min(txPage, totalPages);
                const pageRows = filteredRows.slice((safePage - 1) * TX_PAGE_SIZE, safePage * TX_PAGE_SIZE);

                return filteredRows.length > 0 ? (
                  <div className="overflow-x-auto">
                    <table className="w-full">
                      <thead>
                        <tr className="text-left text-sm text-gray-500 border-b">
                          <th className="pb-3 font-medium text-center w-16">Order #</th>
                          <th className="pb-3 font-medium">Symbol</th>
                          <th className="pb-3 font-medium">Action</th>
                          <th className="pb-3 font-medium">Date & Time</th>
                          <th className="pb-3 font-medium text-right">Amount</th>
                          <th className="pb-3 font-medium text-right">Shares</th>
                          <th className="pb-3 font-medium text-center">Type</th>
                        </tr>
                      </thead>
                      <tbody>
                        {pageRows.map(({ tx, originalIdx }, rowIdx) => {
                          const orderGroup = orderGroupMap.get(originalIdx);
                          const txDate = tx.date ? new Date(tx.date) : new Date();
                          const dateStr = txDate.toLocaleDateString('en-US', { month: 'short', day: 'numeric', year: 'numeric' });
                          const timeStr = txDate.toLocaleTimeString('en-US', { hour: '2-digit', minute: '2-digit', hour12: true });
                          const displaySymbol = tx.symbol && tx.symbol !== 'N/A' ? tx.symbol : '—';
                          const isBuyFill = tx.action && (tx.action.includes('BUY FILL') || tx.action.includes('BUY PARTIAL_FILL'));
                          const price = tx.priceFromDescription ? parseFloat(String(tx.priceFromDescription).replace(/,/g, '')) : (tx.price || 0);
                          const shares = isBuyFill && price > 0 && tx.amount ? (Math.abs(tx.amount) / price) : null;

                          return (
                            <tr key={rowIdx} className="border-b last:border-0 hover:bg-gray-50 transition-colors">
                              <td className="py-4 text-center">
                                {orderGroup !== undefined ? (
                                  <span className="inline-flex items-center justify-center w-8 h-8 rounded-full text-xs font-bold bg-violet-100 text-violet-700 border border-violet-200">
                                    {orderGroup}
                                  </span>
                                ) : (
                                  <span className="text-gray-300 text-xs">—</span>
                                )}
                              </td>

                              <td className="py-4">
                                <div className="font-bold text-gray-900">{displaySymbol}</div>
                              </td>

                              <td className="py-4">
                                <div className="font-medium text-gray-900">{tx.action || tx.type}</div>
                                {tx.priceFromDescription && (
                                  <div className="text-xs text-gray-500">at ${tx.priceFromDescription}</div>
                                )}
                              </td>

                              <td className="py-4">
                                <div className="text-gray-900 text-sm font-medium">{dateStr}</div>
                                <div className="text-gray-500 text-xs">{timeStr}</div>
                              </td>

                              <td className="py-4 text-right">
                                <div className={`font-semibold ${tx.amount >= 0 ? 'text-green-600' : 'text-red-600'}`}>
                                  {tx.amount >= 0 ? '+' : ''}${Math.abs(tx.amount).toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })}
                                </div>
                              </td>

                              <td className="py-4 text-right">
                                {shares !== null
                                  ? <div className="font-medium text-gray-900">{shares.toLocaleString(undefined, { maximumFractionDigits: 4 })}</div>
                                  : <div className="text-gray-400">—</div>}
                              </td>

                              <td className="py-4 text-center">
                                <span className={`inline-block px-2 py-1 rounded text-xs font-medium ${tx.type === 'BUY' ? 'bg-blue-100 text-blue-700' :
                                  tx.type === 'SELL' ? 'bg-orange-100 text-orange-700' :
                                    tx.type === 'FEE' ? 'bg-gray-100 text-gray-700' :
                                      tx.type === 'JNLC' ? 'bg-green-100 text-green-700' :
                                        'bg-gray-100 text-gray-700'
                                  }`}>
                                  {tx.type === 'JNLC' ? 'DEPOSIT' : safeText(tx.type)}
                                </span>
                              </td>
                            </tr>
                          );
                        })}
                      </tbody>
                    </table>

                    {/* ── Pagination bar ── */}
                    <div className="mt-5 flex items-center justify-between border-t border-gray-100 pt-4">
                      <p className="text-sm text-gray-500">
                        Showing{' '}
                        <span className="font-medium text-gray-700">
                          {(safePage - 1) * TX_PAGE_SIZE + 1}–{Math.min(safePage * TX_PAGE_SIZE, filteredRows.length)}
                        </span>{' '}
                        of <span className="font-medium text-gray-700">{filteredRows.length}</span> transactions
                      </p>

                      <div className="flex items-center gap-1">
                        {/* Prev */}
                        <button
                          onClick={() => setTxPage(p => Math.max(1, p - 1))}
                          disabled={safePage === 1}
                          className="px-3 py-1.5 rounded-md text-sm font-medium border border-gray-200 bg-white text-gray-600 hover:bg-gray-50 disabled:opacity-40 disabled:cursor-not-allowed transition-colors"
                        >
                          ← Prev
                        </button>

                        {/* Page number pills */}
                        {Array.from({ length: totalPages }, (_, i) => i + 1)
                          .filter(p => p === 1 || p === totalPages || Math.abs(p - safePage) <= 1)
                          .reduce((acc, p, idx, arr) => {
                            if (idx > 0 && p - arr[idx - 1] > 1) acc.push('…');
                            acc.push(p);
                            return acc;
                          }, [])
                          .map((item, idx) =>
                            item === '…' ? (
                              <span key={`ellipsis-${idx}`} className="px-2 text-gray-400 text-sm">…</span>
                            ) : (
                              <button
                                key={item}
                                onClick={() => setTxPage(item)}
                                className={`w-8 h-8 rounded-md text-sm font-medium transition-colors ${item === safePage
                                  ? 'bg-blue-600 text-white'
                                  : 'border border-gray-200 bg-white text-gray-600 hover:bg-gray-50'
                                  }`}
                              >
                                {item}
                              </button>
                            )
                          )}

                        {/* Next */}
                        <button
                          onClick={() => setTxPage(p => Math.min(totalPages, p + 1))}
                          disabled={safePage === totalPages}
                          className="px-3 py-1.5 rounded-md text-sm font-medium border border-gray-200 bg-white text-gray-600 hover:bg-gray-50 disabled:opacity-40 disabled:cursor-not-allowed transition-colors"
                        >
                          Next →
                        </button>
                      </div>
                    </div>
                  </div>
                ) : (
                  <div className="text-center py-12">
                    <div className="text-gray-400 mb-2">
                      <Search className="w-12 h-12 mx-auto mb-3" />
                    </div>
                    <p className="text-gray-500 font-medium">No transactions match your filters</p>
                    <p className="text-gray-400 text-sm mt-1">Try adjusting your filter criteria</p>
                  </div>
                );
              })()}
            </section>
          </div>

          <aside className="space-y-6">
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