export const CHART_TIMEFRAMES = [
  { value: 10, label: '10D' },
  { value: 30, label: '1M' },
  { value: 90, label: '3M' },
  { value: 180, label: '6M' },
  { value: 365, label: '1Y' },
  { value: 'all', label: 'All' },
];

export const parseChartDate = (value) => {
  if (value instanceof Date) return value;
  const text = String(value || '');
  const match = text.match(/^(\d{4})-(\d{2})-(\d{2})/);
  if (match) {
    const [, year, month, day] = match;
    return new Date(Number(year), Number(month) - 1, Number(day));
  }
  return new Date(text);
};

export const getValueAtDate = (data, targetDate) => {
  const target = targetDate.getTime();
  const sorted = [...data].sort((a, b) => a.date - b.date);
  for (let i = 0; i < sorted.length; i++) {
    if (sorted[i].date.getTime() >= target) {
      if (i === 0) return sorted[0].value;
      const prev = sorted[i - 1];
      const curr = sorted[i];
      const span = curr.date.getTime() - prev.date.getTime();
      if (!span) return curr.value;
      const ratio = (target - prev.date.getTime()) / span;
      return prev.value + (curr.value - prev.value) * ratio;
    }
  }
  return sorted[sorted.length - 1]?.value || 0;
};

export const mapHistorySeries = (rows) => (
  (rows || []).map((item) => ({
    date: parseChartDate(item.date),
    value: Number(item.value) || 0,
  }))
);

export const calculateReturns = (data) => {
  if (!data || data.length === 0) return [];
  const firstValue = data[0].value;
  if (!firstValue || firstValue === 0) return data.map((d) => ({ ...d, value: 0 }));
  return data.map((d) => ({ ...d, value: ((d.value - firstValue) / firstValue) * 100 }));
};

export const normalizeBenchmark = (portfolioData, benchmarkData) => {
  if (!portfolioData?.length || !benchmarkData?.length) return benchmarkData;
  const portfolioFirst = portfolioData[0].value;
  const benchmarkFirst = getValueAtDate(benchmarkData, portfolioData[0].date);
  if (!portfolioFirst || !benchmarkFirst) return benchmarkData;
  const scale = portfolioFirst / benchmarkFirst;
  return benchmarkData.map((d) => ({ ...d, value: d.value * scale }));
};

const computeDailyReturns = (series) => {
  const returns = [];
  for (let i = 1; i < series.length; i++) {
    const prev = series[i - 1].value;
    const curr = series[i].value;
    if (prev > 0) returns.push((curr - prev) / prev);
  }
  return returns;
};

export const calculatePerformanceMetrics = (portfolioSeries, benchmarkSeries) => {
  if (!portfolioSeries || portfolioSeries.length < 2) {
    return { sharpeRatio: 0, maxDrawdown: 0, volatility: 0, beta: 0, alpha: 0, winRate: 0 };
  }

  const portfolioReturns = computeDailyReturns(portfolioSeries);
  const benchmarkReturns = benchmarkSeries?.length > 1 ? computeDailyReturns(benchmarkSeries) : [];

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
    let covariance = 0;
    let benchmarkVariance = 0;
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

  const winRate = portfolioReturns.length > 0
    ? (portfolioReturns.filter((r) => r > 0).length / portfolioReturns.length) * 100
    : 0;

  return {
    sharpeRatio: sharpeRatio || 0,
    maxDrawdown: maxDrawdown * 100 || 0,
    volatility: volatility || 0,
    beta: beta || 0,
    alpha: alpha || 0,
    winRate: winRate || 0,
  };
};
