export const formatProfileDate = (value) => {
  if (!value) return '—';
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return String(value).slice(0, 10);
  return date.toLocaleDateString(undefined, { year: 'numeric', month: 'short', day: 'numeric' });
};

export const getUserInitials = (name) => {
  const text = String(name || '').trim();
  if (!text) return 'U';
  const parts = text.split(/\s+/).filter(Boolean);
  if (parts.length >= 2) return `${parts[0][0]}${parts[1][0]}`.toUpperCase();
  return text.slice(0, 2).toUpperCase();
};

export const safeText = (val) => {
  if (val === null || val === undefined) return '';
  if (typeof val === 'object') {
    if (val.symbol || val.raw_symbol) return val.symbol || val.raw_symbol;
    try { return JSON.stringify(val); } catch { return String(val); }
  }
  return String(val);
};

export const pnlTextClass = (value) => (
  value > 0 ? 'text-green-600' : value < 0 ? 'text-red-600' : 'text-gray-600'
);

export const pnlBadgeClass = (value) => (
  value > 0 ? 'bg-green-100 text-green-700' : value < 0 ? 'bg-red-100 text-red-700' : 'bg-gray-100 text-gray-700'
);

export const formatTxDateTime = (dateValue) => {
  const txDate = dateValue ? new Date(dateValue) : new Date();
  return {
    dateStr: txDate.toLocaleDateString('en-US', { month: 'short', day: 'numeric', year: 'numeric' }),
    timeStr: txDate.toLocaleTimeString('en-US', { hour: '2-digit', minute: '2-digit', hour12: true }),
  };
};
