import React from 'react';
import { Clock, Inbox } from 'lucide-react';

/**
 * Recent activity feed.
 *
 * Takes an explicit list. It used to fall back to two invented rows
 * ("Dr. Vance posted new announcement"), which meant a screen with no data
 * still looked populated. An empty feed now says so.
 */
const ActivityFeed = ({ activities = [] }) => {
  const items = (activities || []).filter(Boolean).slice(0, 4);

  return (
    <div className="fet-card p-4 md:p-5">
      <h3 className="text-[14px] md:text-[15px] font-semibold text-text-primary flex items-center gap-2 mb-4">
        <Clock size={16} className="text-primary" strokeWidth={2} />
        Recent Activity
      </h3>
      {items.length === 0 ? (
        <div className="text-center py-6">
          <Inbox size={26} className="mx-auto text-text-secondary/40" />
          <p className="text-[13px] text-text-secondary mt-2">Nothing recent yet</p>
        </div>
      ) : (
        <div className="space-y-1">
          {items.map((activity, i) => (
            <div key={activity.id || i} className="flex gap-3 p-2.5 rounded-lg hover:bg-page-bg transition-colors">
              <div
                className="w-8 h-8 rounded-lg flex items-center justify-center flex-shrink-0"
                style={{ backgroundColor: 'rgba(63,53,181,0.08)' }}
              >
                <span className="text-[13px]">{activity.system ? '⚙' : '👤'}</span>
              </div>
              <div className="flex-1 min-w-0">
                <p className="text-[13px] text-text-primary">
                  <span className="font-semibold">{activity.user}</span>{' '}
                  <span className="text-text-secondary">{activity.action}</span>
                </p>
                {activity.time ? (
                  <p className="text-[11px] text-text-secondary mt-0.5">{activity.time}</p>
                ) : null}
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
};

export default ActivityFeed;
