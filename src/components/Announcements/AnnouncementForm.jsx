import React, { useState } from 'react';
import { announcementsApi } from '../../lib/announcements';
import { errorMessage } from '../../lib/enrollment';
import { formatDateTime } from '../../lib/format';

const SCOPES = [
  { value: 'FACULTY', label: 'Whole faculty' },
  { value: 'DEPARTMENT', label: 'My department' },
  { value: 'COURSE', label: 'A course' },
];

/**
 * Posts to the real announcements endpoint.
 *
 * It used to write into the client-side mock store with a hardcoded author
 * name, and it expected `onClose`/`onSuccess` while its caller passes
 * `onCancel`/`onSaved`, so submitting called an undefined function and threw.
 */
const AnnouncementForm = ({ onCancel, onSaved, courses = [] }) => {
  const [form, setForm] = useState({
    title: '',
    content: '',
    scope_type: 'FACULTY',
    course_offering: '',
    expires_at: '',
  });
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');

  const submit = async (e) => {
    e.preventDefault();
    setBusy(true);
    setError('');
    try {
      const payload = {
        title: form.title.trim(),
        content: form.content.trim(),
        scope_type: form.scope_type,
        status: 'PUBLISHED',
        published_at: new Date().toISOString(),
      };
      if (form.scope_type === 'COURSE') {
        if (!form.course_offering) {
          setError('Choose the course this announcement is for.');
          setBusy(false);
          return;
        }
        payload.course_offering = form.course_offering;
      }
      if (form.expires_at) payload.expires_at = new Date(form.expires_at).toISOString();
      await announcementsApi.create(payload);
      if (onSaved) onSaved();
    } catch (err) {
      setError(errorMessage(err, 'Could not publish the announcement.'));
    } finally {
      setBusy(false);
    }
  };

  return (
    <form onSubmit={submit} className="space-y-4">
      {error ? (
        <div className="bg-red-50 border border-red-200 text-red-700 px-3 py-2 rounded-lg text-[12.5px]">
          {error}
        </div>
      ) : null}

      <div>
        <label className="fet-label">Title</label>
        <input
          type="text"
          value={form.title}
          onChange={(e) => setForm({ ...form, title: e.target.value })}
          required
          className="w-full px-4 py-2 fet-input"
        />
      </div>

      <div>
        <label className="fet-label">Content</label>
        <textarea
          value={form.content}
          onChange={(e) => setForm({ ...form, content: e.target.value })}
          rows={4}
          required
          className="w-full px-4 py-2 fet-input resize-none"
        />
      </div>

      <div>
        <label className="fet-label">Audience</label>
        <select
          className="w-full px-4 py-2 fet-select"
          value={form.scope_type}
          onChange={(e) => setForm({ ...form, scope_type: e.target.value })}
        >
          {SCOPES.map((s) => <option key={s.value} value={s.value}>{s.label}</option>)}
        </select>
      </div>

      {form.scope_type === 'COURSE' ? (
        <div>
          <label className="fet-label">Course</label>
          <select
            className="w-full px-4 py-2 fet-select"
            value={form.course_offering}
            onChange={(e) => setForm({ ...form, course_offering: e.target.value })}
          >
            <option value="">Choose a course...</option>
            {courses.map((c) => (
              <option key={c.id} value={c.id}>
                {c.course_code} — {c.course_title}
              </option>
            ))}
          </select>
          <p className="text-[11.5px] text-text-tertiary mt-1">
            Course announcements can only be posted by the lecturer who teaches that course.
          </p>
        </div>
      ) : null}

      <div>
        <label className="fet-label">Expires (optional)</label>
        <input
          type="datetime-local"
          className="w-full px-4 py-2 fet-input"
          value={form.expires_at}
          onChange={(e) => setForm({ ...form, expires_at: e.target.value })}
        />
        {form.expires_at ? (
          <p className="text-[11.5px] text-text-tertiary mt-1">
            Hidden after {formatDateTime(form.expires_at)}.
          </p>
        ) : null}
      </div>

      <div className="flex justify-end gap-3 pt-1">
        <button type="button" onClick={onCancel} className="fet-btn-secondary" disabled={busy}>
          Cancel
        </button>
        <button type="submit" className="fet-btn-primary" disabled={busy}>
          {busy ? 'Publishing...' : 'Publish'}
        </button>
      </div>
    </form>
  );
};

export default AnnouncementForm;
