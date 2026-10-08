import React from 'react';

// Keys are lower-case because that is what the API stores: the project model
// declares `ACTIVE = "active"`, `COMPLETED = "completed"`, and so on. Keying
// these maps upper-case made every lookup miss, so badges fell back to the
// generic style and the status filter matched nothing.
export const STATUS_LABELS = {
  draft: 'Draft',
  active: 'Active',
  completed: 'Completed',
  archived: 'Archived',
};

const STATUS_BADGES = {
  draft: 'fet-badge fet-badge-pending',
  active: 'fet-badge fet-badge-active',
  completed: 'fet-badge fet-badge-completed',
  archived: 'fet-badge fet-badge-inactive',
};

export const statusBadge = (status) => (
  <span className={STATUS_BADGES[status] || 'fet-badge fet-badge-inactive'}>
    {STATUS_LABELS[status] || status || '—'}
  </span>
);

export const statusClassName = (status) => STATUS_BADGES[status] || 'fet-badge fet-badge-inactive';

export const formatDateTime = (value) => {
  if (!value) return 'Not set';
  const d = new Date(value);
  if (Number.isNaN(d.getTime())) return String(value);
  return d.toLocaleString([], { dateStyle: 'medium', timeStyle: 'short' });
};