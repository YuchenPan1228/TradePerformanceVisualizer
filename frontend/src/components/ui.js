export const LoadingScreen = ({ message }) => (
  <div className="min-h-screen bg-gray-50 flex items-center justify-center">
    <div className="text-center">
      <div className="animate-spin rounded-full h-12 w-12 border-b-2 border-blue-600 mx-auto" />
      <p className="mt-4 text-gray-600">{message}</p>
    </div>
  </div>
);

const RING_CLASS = { blue: 'focus:ring-blue-500', violet: 'focus:ring-violet-500' };

export const FilterSelect = ({ label, value, onChange, children, ringColor = 'blue' }) => (
  <div className="flex-1 min-w-[160px]">
    <label className="block text-sm font-medium text-gray-700 mb-2">{label}</label>
    <select
      value={value}
      onChange={(e) => onChange(e.target.value)}
      className={`w-full px-3 py-2 border border-gray-300 rounded-lg text-sm focus:outline-none focus:ring-2 ${RING_CLASS[ringColor] || RING_CLASS.blue}`}
    >
      {children}
    </select>
  </div>
);

export const SegmentedControl = ({ options, value, onChange, size = 'md' }) => {
  const containerClass = size === 'sm'
    ? 'flex rounded-lg border border-gray-200 overflow-hidden text-xs font-medium'
    : 'flex rounded-lg border border-gray-200 overflow-hidden text-sm font-medium shadow-sm';

  return (
    <div className={containerClass}>
      {options.map((option, index) => (
        <button
          key={option.id}
          type="button"
          onClick={() => onChange(option.id)}
          className={`${size === 'sm' ? 'flex-1 px-2 py-2' : 'px-5 py-2'} transition-colors ${
            index > 0 && size !== 'sm' ? 'border-l border-gray-200 ' : ''
          }${
            value === option.id
              ? 'bg-blue-600 text-white'
              : size === 'sm'
                ? 'bg-white text-gray-600 hover:bg-gray-50'
                : 'bg-white text-gray-500 hover:bg-gray-50'
          }`}
        >
          {option.label}
        </button>
      ))}
    </div>
  );
};
