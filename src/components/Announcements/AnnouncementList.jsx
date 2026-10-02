import React, { useState, useEffect, useCallback } from 'react';
import { Plus, X, Trash2, Bell, Pin, RefreshCw, Loader2, Megaphone } from 'lucide-react';
import AnnouncementForm from './AnnouncementForm';
import { announcementsApi } from '../../lib/announcements';
import { learningApi } from '../../lib/learning';
import { normalizeRole } from '../../lib/profile';
import {
  SectionHeader, Card, Tag, Pill, Avatar, AvatarStack, Callout, EmptyState, Eyebrow,
} from '../UI';

const TONES = ['#3C5F9E', '#1F7355', '#8E5C0C', '#8A4661', '#4A5261'];

const formatDate = (iso) => {
  if (!iso) return '';
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return '';
  return d.toLocaleDateString(undefined, { day: 'numeric', month: 'long', year: 'numeric' });
};

const AnnouncementList = ({ user }) => {
  const [items, setItems] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [busyId, setBusyId] = useState(null);
  const [showForm, setShowForm] = useState(false);
  // Needed so a course-scoped announcement can name a course.
  const [myOfferings, setMyOfferings] = useState([]);
  const role = normalizeRole(user?.role);
  const canPost = role === 'lecturer' || role === 'admin';

  useEffect(() => {
    if (!canPost) return;
    let cancelled = false;
    (async () => {
      try {
        const data = await learningApi.getMyCourses(role);
        if (!cancelled) setMyOfferings(data || []);
      } catch {
        /* the picker just stays empty; faculty scope still works */
      }
    })();
    return () => { cancelled = true; };
  }, [canPost, role]);

  const load = useCallback(async () => {
    setLoading(true);
    setError('');
    try {
      const data = await announcementsApi.list();
      setItems(Array.isArray(data) ? data : []);
    } catch (err) {
      setError(err.response?.data?.error?.message || 'Could not load announcements.');
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { load(); }, [load]);

  // Opening an announcement is what marks it read, so receipts stay honest.
  const markRead = async (id) => {
    const target = items.find((a) => a.id === id);
    if (!target || target.is_read) return;
    setItems((prev) => prev.map((a) => (a.id === id ? { ...a, is_read: true, read_count: a.read_count + 1 } : a)));
    try {
      await announcementsApi.markRead(id);
    } catch {
      setItems((prev) => prev.map((a) => (a.id === id ? { ...a, is_read: false, read_count: a.read_count - 1 } : a)));
    }
  };

  const togglePin = async (item) => {
    setBusyId(item.id);
    setError('');
    try {
      await announcementsApi.setPinned(item.id, !item.is_pinned);
      await load();
    } catch (err) {
      setError(err.response?.data?.error?.message || 'Could not change the pin.');
    } finally {
      setBusyId(null);
    }
  };

  const remove = async (item) => {
    if (!window.confirm(`Remove "${item.title}"?`)) return;
    setBusyId(item.id);
    setError('');
    try {
      await announcementsApi.remove(item.id);
      await load();
    } catch (err) {
      setError(err.response?.data?.error?.message || 'Could not remove the announcement.');
    } finally {
      setBusyId(null);
    }
  };

  const handleSaved = async () => {
    setShowForm(false);
    await load();
  };

  const pinned = items.find((a) => a.is_pinned) || null;
  const rest = pinned ? items.filter((a) => a.id !== pinned.id) : items;
  const unread = items.filter((a) => !a.is_read).length;

  const Receipt = ({ item }) => {
    const total = item.recipient_count || 0;
    const read = item.read_count || 0;
    const pct = total > 0 ? Math.round((read / total) * 100) : 0;
    const people = (item.readers || []).map((r) => ({ name: r.full_name || r.user_name }));
    return (
      <div className="ui-receipt">
        {people.length ? (
          <AvatarStack people={people} max={4} size={21} tones={TONES} />
        ) : null}
        <span className="tally">{read} of {total} read</span>
        <span className="ui-tally-bar"><i style={{ width: `${pct}%` }} /></span>
      </div>
    );
  };

  return (
    <div className="space-y-4">
      <SectionHeader
        area="announcements"
        icon={Megaphone}
        title="Announcements"
        subtitle="Send to one course or to the whole faculty."
        crumb={[{ label: 'FET Platform' }, { label: 'Announcements' }]}
        actions={canPost ? (
          <button type="button" onClick={() => setShowForm(true)} className="fet-btn-primary">
            <Plus size={15} /> New announcement
          </button>
        ) : null}
      />

      {error ? <Callout tone="bd" icon={AlertCircleIcon}>{error}</Callout> : null}

      {loading ? (
        <Card accent="announcements">
          <div className="flex items-center justify-center gap-2 py-12 text-sm text-text-secondary">
            <Loader2 size={16} className="animate-spin" /> Loading announcements...
          </div>
        </Card>
      ) : null}

      {!loading && items.length === 0 ? (
        <Card accent="announcements">
          <EmptyState
            icon={Megaphone}
            title="Nothing has been posted yet"
            subtitle={canPost
              ? 'Post a notice and it appears here for everyone in the audience you pick.'
              : 'Notices for your courses and department will appear here.'}
            action={canPost ? (
              <button type="button" onClick={() => setShowForm(true)} className="fet-btn-primary">
                <Plus size={15} /> New announcement
              </button>
            ) : null}
          />
        </Card>
      ) : null}

      {unread > 0 ? (
        <div className="flex items-center gap-2">
          <Pill tone="in">{unread} unread</Pill>
        </div>
      ) : null}

      {/* The pinned announcement is the one card that must be seen. */}
      {pinned ? (
        <div className="ui-hero">
          <div className="ui-hero-wash">
            <span className="ui-ribbon"><Pin size={12} /> Pinned</span>
            <button
              type="button"
              onClick={() => markRead(pinned.id)}
              className="mt-3 block w-full text-left"
            >
              <div className="ui-hero-title">{pinned.title}</div>
              <p className="ui-hero-body">{pinned.content}</p>
            </button>
          </div>
          <div className="ui-card-foot">
            <div className="flex min-w-0 items-center gap-2">
              <Avatar name={pinned.creator_name} size={30} tone="#5F2F44" />
              <span className="truncate text-[12.5px] text-text-secondary">
                <b className="text-text-primary">{pinned.creator_name}</b>
                {' '}· {pinned.audience_label}
              </span>
            </div>
            <div className="flex flex-wrap items-center gap-2">
              {pinned.can_manage ? <Receipt item={pinned} /> : null}
              {pinned.can_manage ? (
                <>
                  <button
                    type="button"
                    onClick={() => togglePin(pinned)}
                    disabled={busyId === pinned.id}
                    className="fet-btn-secondary"
                    style={{ padding: '6px 11px', fontSize: 12.5 }}
                  >
                    {busyId === pinned.id ? <Loader2 size={14} className="animate-spin" /> : <X size={14} />} Unpin
                  </button>
                  <button
                    type="button"
                    onClick={() => remove(pinned)}
                    disabled={busyId === pinned.id}
                    className="fet-btn-danger"
                    style={{ padding: '6px 11px', fontSize: 12.5 }}
                  >
                    <Trash2 size={14} /> Remove
                  </button>
                </>
              ) : null}
            </div>
          </div>
        </div>
      ) : null}

      <div className="space-y-4">
        {rest.map((item) => {
          const expired = item.is_expired;
          return (
            <div
              key={item.id}
              className={`ui-ann ${item.is_read ? 'ui-ann-read' : 'ui-ann-unread'}`}
            >
              <div className="ui-ann-top">
                <Avatar name={item.creator_name} size={34} tone={item.is_read ? '#4A5261' : '#8A4661'} />
                <div className="min-w-0 flex-1">
                  <div className="mb-1 flex flex-wrap items-center gap-2">
                    <span className="ui-ann-title">{item.title}</span>
                    {!item.is_read ? <Pill tone="in">New</Pill> : null}
                    {item.is_pinned ? <Pill tone="wn">Pinned</Pill> : null}
                  </div>
                  <div className="flex flex-wrap items-center gap-2">
                    <Tag>{item.audience_label}</Tag>
                    <span className="text-[11.5px] text-text-muted">{formatDate(item.published_at)}</span>
                    {expired ? <Pill tone="wn" dot>Expired</Pill> : null}
                  </div>
                </div>
                {item.can_manage ? (
                  <div className="flex shrink-0 items-center gap-1.5">
                    <button
                      type="button"
                      onClick={() => togglePin(item)}
                      disabled={busyId === item.id}
                      className="fet-btn-secondary"
                      style={{ padding: '6px 10px' }}
                      title={item.is_pinned ? 'Unpin' : 'Pin to the top'}
                      aria-label={item.is_pinned ? `Unpin ${item.title}` : `Pin ${item.title}`}
                    >
                      <Pin size={15} />
                    </button>
                    <button
                      type="button"
                      onClick={() => remove(item)}
                      disabled={busyId === item.id}
                      className="fet-btn-danger"
                      style={{ padding: '6px 10px' }}
                      aria-label={`Remove ${item.title}`}
                    >
                      <Trash2 size={15} />
                    </button>
                  </div>
                ) : null}
              </div>

              <button
                type="button"
                onClick={() => markRead(item.id)}
                className="block w-full text-left"
                disabled={item.is_read}
              >
                <p className="ui-ann-body">{item.content}</p>
              </button>

              <div className="ui-ann-foot">
                <span className="text-[11.5px] text-text-muted">
                  Posted by {item.creator_name}
                </span>
                <div className="flex-1" />
                {item.can_manage ? <Receipt item={item} /> : null}
              </div>
            </div>
          );
        })}
      </div>

      {showForm ? (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 p-4">
          <div className="max-h-[90vh] w-full max-w-2xl overflow-y-auto rounded-lg bg-surface shadow-modal">
            <div className="flex items-center justify-between border-b border-border-default p-5">
              <h3 className="text-[15px] font-bold text-text-primary">New announcement</h3>
              <button
                type="button"
                onClick={() => setShowForm(false)}
                className="rounded-md p-1 transition-colors hover:bg-page-bg"
                aria-label="Close"
              >
                <X size={20} className="text-text-secondary" />
              </button>
            </div>
            <div className="p-5">
              <AnnouncementForm
                courses={myOfferings}
                onCancel={() => setShowForm(false)}
                onSaved={handleSaved}
              />
            </div>
          </div>
        </div>
      ) : null}
    </div>
  );
};

/* Small local icon so the error callout matches the rest of the app. */
function AlertCircleIcon(props) {
  return (
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.9"
         strokeLinecap="round" strokeLinejoin="round" aria-hidden="true" {...props}>
      <circle cx="12" cy="12" r="9" />
      <line x1="12" y1="8" x2="12" y2="12" />
      <line x1="12" y1="16" x2="12.01" y2="16" />
    </svg>
  );
}

export default AnnouncementList;
