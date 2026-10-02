import React from 'react';

export const STATUS_LABELS = {
  DRAFT: 'Draft',
  ACTIVE: 'Active',
  COMPLETED: 'Completed',
  ARCHIVED: 'Archived',
};

const STATUS_BADGES = {
  DRAFT: 'fet-badge fet-badge-pending',
  ACTIVE: 'fet-badge fet-badge-active',
  COMPLETED: 'fet-badge fet-badge-completed',
  ARCHIVED: 'fet-badge fet-badge-inactive',
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