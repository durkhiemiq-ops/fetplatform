import React from 'react';

const StatsCard = ({ icon: Icon, label, value, color = 'secondary' }) => {
  const colorMap = {
    secondary: { bg: 'rgba(63,53,181,0.08)', icon: '#3F35B5' },
    primary: { bg: 'rgba(63,53,181,0.08)', icon: '#3F35B5' },
    tertiary: { bg: 'rgba(139,92,246,0.08)', icon: '#8B5CF6' },
    success: { bg: 'rgba(22,163,74,0.08)', icon: '#16A34A' },
    warning: { bg: 'rgba(245,158,11,0.08)', icon: '#F59E0B' },
    error: { bg: 'rgba(220,38,38,0.08)', icon: '#DC2626' },
    info: { bg: 'rgba(37,99,235,0.08)', icon: '#2563EB' },
  };

  const colors = colorMap[color] || colorMap.secondary;

  return (
    <div className="fet-card p-4 md:p-5 hover:shadow-card-hover transition-shadow">
      <div className="flex items-center gap-3 md:gap-4">
        <div className="p-2.5 md:p-3 rounded-xl flex-shrink-0" style={{ backgroundColor: colors.bg }}>
          <Icon className="w-5 h-5 md:w-[22px] md:h-[22px]" style={{ color: colors.icon }} strokeWidth={2} />
        </div>
        <div className="flex-1 min-w-0">
          <p className="text-[20px] md:text-[24px] font-bold text-text-primary leading-tight">{value}</p>
          <p className="text-[12px] text-text-secondary font-medium truncate mt-0.5">{label}</p>
        </div>
      </div>
    </div>
  );
};

export default StatsCard;
