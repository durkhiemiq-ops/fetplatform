import React from 'react';
import { Clock } from 'lucide-react';

const ActivityFeed = ({ activities }) => {
  const defaultActivities = [
    { user: 'System', action: 'Welcome to FET Platform', time: 'Just now' },
    { user: 'Dr. Vance', action: 'posted new announcement', time: '1 hour ago' },
  ];

  const items = activities && activities.length > 0 ? activities : defaultActivities;

  return (
    <div className="fet-card p-4 md:p-5">
      <h3 className="text-[14px] md:text-[15px] font-semibold text-text-primary flex items-center gap-2 mb-4">
        <Clock size={16} className="text-primary" strokeWidth={2} />
        Recent Activity
      </h3>
      <div className="space-y-1">
        {items.slice(0, 4).map((activity, i) => (
          <div key={i} className="flex gap-3 p-2.5 rounded-lg hover:bg-page-bg transition-colors">
            <div className="w-8 h-8 rounded-lg flex items-center justify-center flex-shrink-0" style={{ backgroundColor: 'rgba(63,53,181,0.08)' }}>
              <span className="text-[13px]">
                {activity.user === 'System' ? '⚙' : '👤'}
              </span>
            </div>
            <div className="flex-1 min-w-0">
              <p className="text-[13px] text-text-primary">
                <span className="font-semibold">{activity.user}</span>{' '}
                <span className="text-text-secondary">{activity.action}</span>
              </p>
              <p className="text-[11px] text-text-secondary mt-0.5">{activity.time}</p>
            </div>
          </div>
        ))}
      </div>
    </div>
  );
};

export default ActivityFeed;
