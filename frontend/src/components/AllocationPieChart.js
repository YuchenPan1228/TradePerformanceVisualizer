const PIE_COLORS = [
  '#3b82f6', '#10b981', '#f59e0b', '#ef4444', '#8b5cf6',
  '#ec4899', '#14b8a6', '#6366f1', '#84cc16', '#f97316',
];

const polarToCartesian = (cx, cy, radius, angleDeg) => {
  const rad = (angleDeg * Math.PI) / 180;
  return { x: cx + radius * Math.cos(rad), y: cy + radius * Math.sin(rad) };
};

const describePieSlice = (cx, cy, radius, startAngle, endAngle) => {
  if (endAngle - startAngle >= 359.99) {
    return `M ${cx - radius} ${cy} A ${radius} ${radius} 0 1 1 ${cx + radius} ${cy} A ${radius} ${radius} 0 1 1 ${cx - radius} ${cy} Z`;
  }
  const start = polarToCartesian(cx, cy, radius, endAngle);
  const end = polarToCartesian(cx, cy, radius, startAngle);
  const largeArc = endAngle - startAngle > 180 ? 1 : 0;
  return `M ${cx} ${cy} L ${start.x} ${start.y} A ${radius} ${radius} 0 ${largeArc} 0 ${end.x} ${end.y} Z`;
};

const groupAllocationEntries = (entries, maxSlices = 8) => {
  const sorted = entries
    .filter((entry) => entry.value > 0)
    .sort((a, b) => b.value - a.value);
  if (sorted.length <= maxSlices) return sorted;
  const kept = sorted.slice(0, maxSlices - 1);
  const otherValue = sorted.slice(maxSlices - 1).reduce((sum, entry) => sum + entry.value, 0);
  if (otherValue > 0) kept.push({ label: 'Other', value: otherValue });
  return kept;
};

export const buildPieSlices = (entries, maxSlices = 8) => {
  const grouped = groupAllocationEntries(entries, maxSlices);
  const total = grouped.reduce((sum, entry) => sum + entry.value, 0);
  if (!total) return [];

  let angle = -90;
  return grouped.map((entry, index) => {
    const sweep = (entry.value / total) * 360;
    const startAngle = angle;
    const endAngle = angle + sweep;
    angle = endAngle;
    return {
      ...entry,
      color: PIE_COLORS[index % PIE_COLORS.length],
      percent: (entry.value / total) * 100,
      path: describePieSlice(100, 100, 78, startAngle, endAngle),
    };
  });
};

export const buildGroupedAllocationSlices = (holdings, cashBalance, keyFn, fallbackKey) => {
  const buckets = {};
  holdings.forEach((holding) => {
    const key = keyFn(holding) || fallbackKey;
    buckets[key] = (buckets[key] || 0) + holding.marketValue;
  });
  if (cashBalance > 0) buckets.Cash = (buckets.Cash || 0) + cashBalance;
  return buildPieSlices(
    Object.entries(buckets).map(([label, value]) => ({ label, value }))
  );
};

const AllocationPieChart = ({ slices }) => {
  if (!slices.length) {
    return <div className="text-sm text-gray-500 text-center py-8">No allocation data</div>;
  }

  return (
    <div className="flex flex-col items-center gap-4">
      <svg viewBox="0 0 200 200" className="w-44 h-44">
        {slices.map((slice, index) => (
          <path key={`${slice.label}-${index}`} d={slice.path} fill={slice.color} stroke="#fff" strokeWidth="1.5" />
        ))}
      </svg>
      <div className="w-full space-y-2">
        {slices.map((slice, index) => (
          <div key={`${slice.label}-${index}`} className="flex items-center justify-between text-sm">
            <div className="flex items-center gap-2 min-w-0">
              <span className="w-2.5 h-2.5 rounded-full flex-shrink-0" style={{ backgroundColor: slice.color }} />
              <span className="text-gray-700 truncate">{slice.label}</span>
            </div>
            <div className="text-right flex-shrink-0 ml-2">
              <span className="font-medium text-gray-900">{slice.percent.toFixed(1)}%</span>
              <span className="text-gray-500 ml-2">${slice.value.toLocaleString(undefined, { maximumFractionDigits: 0 })}</span>
            </div>
          </div>
        ))}
      </div>
    </div>
  );
};

export default AllocationPieChart;
