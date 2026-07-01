import React from 'react';
import {
  CHART_TIMEFRAMES,
  getValueAtDate,
  calculateReturns,
  normalizeBenchmark,
  calculatePerformanceMetrics,
} from '../utils/chart';
import { pnlTextClass } from '../utils/format';

const PerformanceGraph = ({
  growthData,
  benchmarkData,
  yAxisType,
  setYAxisType,
  benchmark,
  setBenchmark,
  showStockFilter,
  setShowStockFilter,
  availableStocks,
  selectedStocks,
  setSelectedStocks,
  timeframe,
  setTimeframe,
  hoveredPoint,
  setHoveredPoint,
}) => {
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
    ...portfolioPoints.map((p) => p.date.getTime()),
    ...benchmarkPoints.map((p) => p.date.getTime()),
  ])].sort((a, b) => a - b);

  if (allDates.length === 0) {
    return <div className="bg-white rounded-2xl p-6 shadow-sm"><div className="text-center py-12 text-gray-500">No data available</div></div>;
  }

  const portfolioSeries = allDates.map((date) => ({
    date: new Date(date),
    value: getValueAtDate(portfolioPoints, new Date(date)),
  }));
  const benchmarkSeries = benchmarkPoints.length > 0
    ? allDates.map((date) => ({
      date: new Date(date),
      value: getValueAtDate(benchmarkPoints, new Date(date)),
    }))
    : [];

  const allValues = [
    ...portfolioSeries.map((p) => p.value),
    ...benchmarkSeries.map((p) => p.value),
  ].filter((v) => !isNaN(v) && isFinite(v));

  if (allValues.length === 0) {
    return <div className="bg-white rounded-2xl p-6 shadow-sm"><div className="text-center py-12 text-gray-500">No valid data points</div></div>;
  }

  const yMin = Math.min(...allValues);
  const yMax = Math.max(...allValues);
  const yPad = (yMax - yMin) * 0.1 || 1;
  const y0 = yMin - yPad;
  const y1 = yMax + yPad;

  const sx = (i) => padding + (i / (allDates.length - 1 || 1)) * (width - padding * 2);
  const sy = (y) => padding + (1 - (y - y0) / (y1 - y0 || 1)) * (height - padding * 2);

  const portfolioPath = portfolioSeries.map((p, i) => `${i === 0 ? 'M' : 'L'} ${sx(i)} ${sy(p.value)}`).join(' ');
  const benchmarkPath = benchmarkSeries.length > 0
    ? benchmarkSeries.map((p, i) => `${i === 0 ? 'M' : 'L'} ${sx(i)} ${sy(p.value)}`).join(' ')
    : '';

  const firstPortfolio = portfolioSeries[0]?.value ?? 0;
  const lastPortfolio = portfolioSeries[portfolioSeries.length - 1]?.value ?? 0;
  const portfolioReturn = firstPortfolio ? ((lastPortfolio - firstPortfolio) / Math.abs(firstPortfolio)) * 100 : 0;

  const metrics = calculatePerformanceMetrics(growthData || [], benchmarkData || []);

  const formatYValue = (val) => (yAxisType === 'return'
    ? `${val >= 0 ? '+' : ''}${val.toFixed(2)}%`
    : `$${val.toLocaleString(undefined, { maximumFractionDigits: 0 })}`);

  return (
    <div className="bg-white rounded-2xl p-6 shadow-sm">
      <div className="mb-6">
        <h2 className="text-2xl font-bold text-gray-900 mb-2">Portfolio Performance</h2>
        <div className="text-3xl font-bold text-gray-900 mb-1">
          {yAxisType === 'return'
            ? `${portfolioReturn >= 0 ? '+' : ''}${portfolioReturn.toFixed(2)}%`
            : `$${lastPortfolio.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`}
        </div>
        <div className={`text-sm ${pnlTextClass(portfolioReturn)}`}>
          {portfolioReturn >= 0 ? '+' : ''}{portfolioReturn.toFixed(2)}% ({portfolioReturn >= 0 ? '+' : ''}{(lastPortfolio - firstPortfolio).toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })}) Today
        </div>
        <div className="text-xs text-gray-500 mt-1">
          Closed: {new Date().toLocaleString('en-US', { month: 'short', day: 'numeric', hour: 'numeric', minute: 'numeric', timeZoneName: 'short' })}
        </div>
      </div>

      <div className="border-t border-gray-200 pt-4 mb-4" />

      <div className="mb-6 space-y-4">
        <div className="flex flex-wrap gap-4 items-center">
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
                <button onClick={() => setSelectedStocks(new Set(availableStocks.map((s) => s.symbol)))}
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
                      if (e.target.checked) newSelected.add(stock.symbol);
                      else newSelected.delete(stock.symbol);
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
            {[0, 0.25, 0.5, 0.75, 1].map((t) => (
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
            const x = sx(i);
            const y = sy(point.value);
            const benchmarkValue = benchmarkSeries[i]?.value;
            return (
              <g key={i}>
                <rect x={x - 10} y={padding} width={20} height={height - padding * 2} fill="transparent" style={{ cursor: 'crosshair' }}
                  onMouseEnter={() => {
                    setHoveredPoint({
                      x,
                      y,
                      date: point.date,
                      portfolioValue: point.value,
                      benchmarkValue,
                    });
                  }} />
                {hoveredPoint && hoveredPoint.date.getTime() === point.date.getTime() && (
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
            {[0, 0.25, 0.5, 0.75, 1].map((t) => {
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
              const labels = [];
              const labelIndices = new Set();
              if (portfolioSeries.length === 1 || dateRange === 0) {
                const point = portfolioSeries[0];
                return [
                  <text key={0} x={sx(0)} y={height - padding + 20} textAnchor="middle">
                    {point.date.toLocaleDateString('en-US', { month: 'short', day: 'numeric' })}
                  </text>,
                ];
              }
              for (let i = 0; i < numLabels; i++) {
                const targetTime = firstDate + (dateRange * i / (numLabels - 1));
                let closestIdx = 0;
                let minDiff = Math.abs(portfolioSeries[0].date.getTime() - targetTime);
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
                    </text>,
                  );
                }
              }
              return labels;
            })()}
          </g>
        </svg>

        {hoveredPoint && (
          <div className="absolute bg-gray-900 text-white px-3 py-2 rounded-lg shadow-lg text-sm pointer-events-none z-10"
            style={{
              left: `${(hoveredPoint.x / width) * 100}%`,
              top: `${Math.max((hoveredPoint.y / height) * 100 - 8, 0)}%`,
              transform: 'translate(-50%, -100%)',
            }}>
            <div className="font-semibold mb-1">
              {hoveredPoint.date.toLocaleDateString('en-US', { weekday: 'short', month: 'short', day: 'numeric', year: 'numeric' })}
            </div>
            <div className="flex items-center gap-2 mb-1">
              <div className="w-3 h-3 rounded-full bg-blue-600" />
              <span>Portfolio: {formatYValue(hoveredPoint.portfolioValue)}</span>
            </div>
            {hoveredPoint.benchmarkValue !== undefined && (
              <div className="flex items-center gap-2">
                <div className="w-3 h-3 rounded-full bg-green-500" />
                <span>Benchmark: {formatYValue(hoveredPoint.benchmarkValue)}</span>
              </div>
            )}
          </div>
        )}
      </div>

      <div className="flex items-center gap-6 mt-4 pt-4 border-t border-gray-200">
        <div className="flex items-center gap-2">
          <div className="w-4 h-0.5 bg-blue-600" />
          <span className="text-sm text-gray-600">Portfolio</span>
        </div>
        {benchmark !== 'none' && (
          <div className="flex items-center gap-2">
            <div className="w-4 h-0.5 bg-green-500 border-dashed border-t-2" />
            <span className="text-sm text-gray-600">Benchmark ({benchmark})</span>
          </div>
        )}
      </div>

      <div className="flex flex-wrap gap-2 mt-6 pt-4 border-t border-gray-200">
        {CHART_TIMEFRAMES.map(({ value, label }) => (
          <button key={label} onClick={() => setTimeframe(value)}
            className={`px-4 py-2 rounded-md text-sm font-medium transition-colors ${timeframe === value ? 'bg-blue-600 text-white' : 'bg-gray-100 text-gray-700 hover:bg-gray-200'}`}>
            {label}
          </button>
        ))}
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

export default PerformanceGraph;
