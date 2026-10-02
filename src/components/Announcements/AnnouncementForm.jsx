import React, { useState } from 'react';
import { useAppContext } from '../../context/AppContext';

/**
 * AnnouncementForm — posts through the real backend contract.
 *
 * AnnouncementCreateSerializer requires {title, body, scope, scope_id}; scope_id
 * is a UUID naming the target and is validated server-side. The old form sent
 * `content` / `type` / `author` and no scope target at all, so every submission
 * was rejected with 400. `type` and `author` do not exist on the model — the
 * backend derives importance from `is_important` and stamps `created_by`.
 */
const AnnouncementForm = ({ onClose, onSuccess }) => {
  const { addAnnouncement, faculties, departments, courses, classSessions } = useAppContext();
  const [formData, setFormData] = useState({
    title: '',
    content: '',
    scope: 'faculty',
    scopeId: '',
    isImportant: false,
    published: true,
  });
  const [error, setError] = useState('');
  const [busy, setBusy] = useState(false);

  // Candidate targets per scope, taken from the already-loaded reference data.
  const targetOptions = {
    faculty: faculties.map((f) => ({ id: f.id, label: f.name })),
    department: departments.map((d) => ({ id: d.id, label: d.name })),
    course: courses.map((c) => ({ id: c.id, label: `${c.code} — ${c.name}` })),
    class: classSessions.map((s) => ({
      id: s.id,
      label: `${s.courseCode} — ${s.startsAt ? new Date(s.startsAt).toLocaleString() : s.id.slice(0, 8)}`,
    })),
  }[formData.scope] || [];

  const handleScopeChange = (scope) => {
    setFormData((prev) => ({ ...prev, scope, scopeId: '' }));
    setError('');
  };

  const handleSubmit = async (e) => {
    e.preventDefault();
    setError('');
    if (!formData.scopeId) {
      setError('Choose which audience this announcement targets.');
      return;
    }
    setBusy(true);
    try {
      await addAnnouncement(formData);
      onSuccess && onSuccess();
    } catch (err) {
      setError(err.message || 'Could not post the announcement.');
    } finally {
      setBusy(false);
    }
  };

  return (
    <form onSubmit={handleSubmit} className="space-y-4">
      {error && (
        <div className="rounded-lg border border-red-200 bg-red-50 px-3 py-2 text-[13px] text-red-700">
          {error}
        </div>
      )}

      <div>
        <label className="fet-label">Title</label>
        <input
          type="text"
          value={formData.title}
          onChange={(e) => setFormData((prev) => ({ ...prev, title: e.target.value }))}
          required
          className="w-full px-4 py-2 fet-input"
        />
      </div>

      <div>
        <label className="fet-label">Content</label>
        <textarea
          value={formData.content}
          onChange={(e) => setFormData((prev) => ({ ...prev, content: e.target.value }))}
          rows={4}
          required
          className="w-full px-4 py-2 fet-input resize-none"
        />
      </div>

      <div>
        <label className="fet-label">Audience scope</label>
        <select
          value={formData.scope}
          onChange={(e) => handleScopeChange(e.target.value)}
          className="w-full px-4 py-2 fet-select"
        >
          <option value="faculty">Faculty (everyone)</option>
          <option value="department">Department</option>
          <option value="course">Course</option>
          <option value="class">Class session</option>
        </select>
        <p className="mt-1 text-[11px] text-text-secondary">
          Who can see this announcement. Scope is enforced server-side from your role and
          enrollment.
        </p>
      </div>

      <div>
        <label className="fet-label">Target *</label>
        <select
          value={formData.scopeId}
          onChange={(e) => setFormData((prev) => ({ ...prev, scopeId: e.target.value }))}
          required
          className="w-full px-4 py-2 fet-select"
        >
          <option value="">Select {formData.scope}…</option>
          {targetOptions.map((opt) => (
            <option key={opt.id} value={opt.id}>
              {opt.label}
            </option>
          ))}
        </select>
        {targetOptions.length === 0 && (
          <p className="mt-1 text-[11px] text-text-secondary">
            No {formData.scope} records are available to target.
          </p>
        )}
      </div>

      <div className="flex items-center gap-2">
        <input
          id="announcement-important"
          type="checkbox"
          checked={formData.isImportant}
          onChange={(e) => setFormData((prev) => ({ ...prev, isImportant: e.target.checked }))}
          className="w-4 h-4 rounded accent-primary"
        />
        <label htmlFor="announcement-important" className="text-[13px] text-text-primary">
          Mark as important
        </label>
      </div>

      <div className="flex justify-end gap-3 pt-4 border-t border-border-default">
        <button type="button" onClick={onClose} className="fet-btn-secondary" disabled={busy}>
          Cancel
        </button>
        <button type="submit" className="fet-btn-primary disabled:opacity-60" disabled={busy || !formData.scopeId}>
          {busy ? 'Posting…' : 'Post Announcement'}
        </button>
      </div>
    </form>
  );
};

export default AnnouncementForm;
