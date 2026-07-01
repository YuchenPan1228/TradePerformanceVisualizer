export const buildOrderGroupMap = (transactions) => {
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

    let lastTime = new Date(fills[i].tx.date).getTime();
    let j = i;

    while (j < fills.length) {
      const sym = fills[j].tx.symbol || '';
      const t = new Date(fills[j].tx.date).getTime();
      if (sym !== anchorSymbol || t - lastTime > 120_000) break;
      map.set(fills[j].idx, group);
      lastTime = t;
      j++;
    }

    i = j;
  }

  return map;
};

export const getUniqueSymbols = (transactions) => {
  const symbols = new Set();
  transactions.forEach((tx) => {
    if (tx.symbol && tx.symbol !== 'N/A') symbols.add(tx.symbol);
  });
  return Array.from(symbols).sort();
};

export const filterTransactions = ({
  transactions,
  transactionView,
  symbolFilter,
  typeFilter,
  dateFilter,
  customDateRange,
  groupFilter,
  orderGroupMap,
}) => {
  let filtered = transactions.map((tx, originalIdx) => ({ tx, originalIdx }));

  filtered = filtered.filter(({ tx }) => {
    const type = tx.type || '';
    const isOptionRelated = Boolean(tx.isOption) || type.includes('OPTIONEXERCISE') || type.includes('OPTRD');
    if (transactionView === 'options') {
      if (tx.source !== 'order' || tx.type !== 'OPTION_ORDER') return false;
      const filledQty = Number(tx.filledQuantity ?? tx.quantity ?? tx.contractCount ?? 0);
      const status = (tx.status || '').toUpperCase();
      const isActive = ['PENDING', 'OPEN', 'NEW', 'ACCEPTED', 'QUEUED', 'WORKING', 'PARTIALLY_FILLED', 'PARTIAL'].includes(status);
      if (filledQty <= 0 && !isActive) return false;
      return true;
    }
    return !isOptionRelated;
  });

  if (symbolFilter !== 'all') {
    filtered = filtered.filter(({ tx }) => tx.symbol === symbolFilter);
  }

  if (typeFilter !== 'all') {
    filtered = filtered.filter(({ tx }) => {
      const act = (tx.action || '').toUpperCase();
      const st = (tx.status || '').toUpperCase();

      if (transactionView === 'options') {
        if (typeFilter === 'buy') return act.includes('BUY');
        if (typeFilter === 'sell') return act.includes('SELL');
        if (typeFilter === 'executed') return st === 'EXECUTED' || st === 'FILLED';
        if (typeFilter === 'expired') return st === 'EXPIRED';
        if (typeFilter === 'canceled') return st === 'CANCELED' || st === 'CANCELLED';
        if (typeFilter === 'pending') {
          return st && !['EXECUTED', 'FILLED', 'EXPIRED', 'CANCELED', 'CANCELLED', 'REJECTED'].includes(st);
        }
        return true;
      }

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
        const weekAgo = new Date(today);
        weekAgo.setDate(weekAgo.getDate() - 7);
        return txDate >= weekAgo;
      }
      if (dateFilter === 'month') {
        const monthAgo = new Date(today);
        monthAgo.setMonth(monthAgo.getMonth() - 1);
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
