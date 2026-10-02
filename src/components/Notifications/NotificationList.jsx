import React, { useState, useEffect, useCallback } from 'react';
import { Bell, Check, BellOff, RefreshCw } from 'lucide-react';
import { SectionHeader, Card, CardBody, CardHead, Pill, EmptyState, Callout } from '../UI';
import { notificationsApi } from '../../lib/notifications';
import { errorMessage } from '../../lib/enrollment';
import { relativeTime } from '../../lib/format';

const TONE = {
  ATTENDANCE: 'in',
  ASSESSMENT: 'warn',
  GRADE: 'warn',
  ANNOUNCEMENT: 'in',
  ENROLLMENT: 'ok',
  CARRY_OVER: 'warn',
};

const NotificationList = () => {
  const [rows, setRows] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [filter, setFilter] = useState('all');

  const load = useCallback(async () => {
    setLoading(true);
    setError('');
    try {
      setRows((await notificationsApi.list(filter === 'unread')) || []);
    } catch (err) {
      setError(errorMessage(err, 'Could not load notifications.'));
    } finally {
      setLoading(false);
    }
  }, [filter]);

  useEffect(() => { load(); }, [load]);

  const unread = rows.filter((n) => !n.read_at).length;

  // The sidebar badge counts unread too, so tell it when that number moves.
  const announce = () => window.dispatchEvent(new Event('fet-notifications-changed'));

  const markRead = async (id) => {
    try {
      await notificationsApi.markRead(id);
      await load();
      announce();
    } catch (err) {
      setError(errorMessage(err, 'Could not mark that as read.'));
    }
  };

  const markAll = async () => {
    try {
      await notificationsApi.markAllRead();
      await load();
      announce();
    } catch (err) {
      setError(errorMessage(err, 'Could not mark all as read.'));
    }
  };

  return (
    <div className="space-y-5">
      <SectionHeader
        area="hub"
        icon={Bell}
        title="Notifications"
        subtitle="Activity the platform raises for you: attendance checkpoints, marks, announcements and enrolment changes."
        actions={(
          <>
            <button type="button" onClick={load} className="fet-btn-secondary" disabled={loading}>
              <RefreshCw size={14} /> Refresh
            </button>
            <button type="button" onClick={markAll} className="fet-btn-primary" disabled={!unread}>
              <Check size={14} /> Mark all read
            </button>
          </>
        )}
      />

      {error ? <Callout tone="bad">{error}</Callout> : null}

      <Card accent="hub">
        <CardHead title="Inbox" square="hub">
          <div className="ui-tabs" style={{ border: 'none', padding: 0 }}>
            <button
              type="button"
              className={`ui-tab${filter === 'all' ? ' active' : ''}`}
              onClick={() => setFilter('all')}
            >
              All
            </button>
            <button
              type="button"
              className={`ui-tab${filter === 'unread' ? ' active' : ''}`}
              onClick={() => setFilter('unread')}
            >
              Unread
              {unread ? <span className="n">{unread}</span> : null}
            </button>
          </div>
        </CardHead>
        <CardBody>
          {loading ? (
            <p className="text-text-secondary text-[13px] py-6 text-center">Loading notifications...</p>
          ) : rows.length === 0 ? (
            <EmptyState
              icon={filter === 'unread' ? Check : BellOff}
              title={filter === 'unread' ? 'Nothing unread' : 'No notifications yet'}
              subtitle={
                filter === 'unread'
                  ? 'You are all caught up.'
                  : 'Notifications appear here when attendance, marks or announcements need your attention.'
              }
            />
          ) : (
            <ul className="space-y-2">
              {rows.map((n) => (
                <li
                  key={n.id}
                  className="ui-li flex items-start gap-3"
                  style={n.read_at ? { opacity: 0.62 } : undefined}
                >
                  <div className="min-w-0 flex-1">
                    <div className="flex items-center gap-2 flex-wrap">
                      <p className="ui-card-title text-[13px]">{n.title}</p>
                      {n.read_at
                        ? <Pill tone="mute">Read</Pill>
                        : <Pill tone="in" dot>New</Pill>}
                      {n.type ? <Pill tone={TONE[n.type] || 'mute'}>{String(n.type).replace(/_/g, ' ')}</Pill> : null}
                    </div>
                    {n.message ? (
                      <p className="ui-sub mt-1">{n.message}</p>
                    ) : null}
                    <p className="text-[11.5px] text-text-tertiary mt-1">{relativeTime(n.created_at)}</p>
                  </div>
                  {!n.read_at ? (
                    <button
                      type="button"
                      onClick={() => markRead(n.id)}
                      className="fet-btn-secondary text-[12px] shrink-0"
                    >
                      Mark read
                    </button>
                  ) : null}
                </li>
              ))}
            </ul>
          )}
        </CardBody>
      </Card>
    </div>
  );
};

export default NotificationList;
