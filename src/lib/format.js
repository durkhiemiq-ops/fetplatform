/** Date/time helpers shared by the newer screens. */

export const formatDate = (value) => {
  if (!value) return 'Not set';
  const d = new Date(value);
  if (Number.isNaN(d.getTime())) return String(value);
  return d.toLocaleDateString([], { dateStyle: 'medium' });
};

export const formatDateTime = (value) => {
  if (!value) return 'Not set';
  const d = new Date(value);
  if (Number.isNaN(d.getTime())) return String(value);
  return d.toLocaleString([], { dateStyle: 'medium', timeStyle: 'short' });
};

/** "3 mins ago" -- the right default for a notification or activity feed. */
export const relativeTime = (value) => {
  if (!value) return '';
  const d = new Date(value);
  if (Number.isNaN(d.getTime())) return String(value);
  const secs = Math.round((Date.now() - d.getTime()) / 1000);
  if (secs < 0) return 'just now';
  if (secs < 60) return `${secs}s ago`;
  const mins = Math.round(secs / 60);
  if (mins < 60) return `${mins} min${mins === 1 ? '' : 's'} ago`;
  const hours = Math.round(mins / 60);
  if (hours < 24) return `${hours} hour${hours === 1 ? '' : 's'} ago`;
  const days = Math.round(hours / 24);
  if (days < 30) return `${days} day${days === 1 ? '' : 's'} ago`;
  return formatDate(value);
};

/** Timetable slots are stored as "HH:MM" and already mean local time. */
export const formatClock = (value) => {
  if (!value) return '';
  const m = /^(\d{1,2}):(\d{2})/.exec(String(value));
  if (!m) return String(value);
  const h = Number(m[1]);
  const suffix = h >= 12 ? 'pm' : 'am';
  const hour12 = h % 12 === 0 ? 12 : h % 12;
  return `${hour12}:${m[2]}${suffix}`;
};
