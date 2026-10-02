import React from 'react';

const RubricItem = ({ label, weight, maxMarks, score, icon: Icon }) => {
  const percentage = maxMarks > 0 ? ((score / maxMarks) * 100).toFixed(0) : 0;

  return (
    <div className="flex items-center justify-between p-4 bg-page-bg rounded-xl hover:bg-primary-light/30 transition-colors">
      <div className="flex items-center gap-3 flex-1">
        {Icon && (
          <div className="p-2 rounded-lg" style={{ backgroundColor: 'rgba(63,53,181,0.08)' }}>
            <Icon size={18} className="text-primary" />
          </div>
        )}
        <div>
          <p className="font-medium text-text-primary">{label}</p>
          <p className="text-xs text-text-secondary">
            Weight: {weight}% | Max Marks: {maxMarks}
          </p>
        </div>
      </div>
      <div className="flex items-center gap-4">
        <div className="text-right">
          <p className="text-lg font-bold text-text-primary">{score}</p>
          <p className="text-xs text-text-secondary">/ {maxMarks}</p>
        </div>
        <div className="w-12 h-12 relative">
          <svg className="w-12 h-12 transform -rotate-90">
            <circle
              cx="24"
              cy="24"
              r="20"
              stroke="#e5e7eb"
              strokeWidth="4"
              fill="none"
            />
            <circle
              cx="24"
              cy="24"
              r="20"
              stroke="#3F35B5"
              strokeWidth="4"
              fill="none"
              strokeDasharray={2 * Math.PI * 20}
              strokeDashoffset={2 * Math.PI * 20 * (1 - Math.min(percentage / 100, 1))}
              strokeLinecap="round"
            />
          </svg>
          <span className="absolute inset-0 flex items-center justify-center text-xs font-bold text-text-primary">
            {percentage}%
          </span>
        </div>
      </div>
    </div>
  );
};

export default RubricItem;