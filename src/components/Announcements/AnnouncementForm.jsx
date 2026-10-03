import React, { useState } from 'react';
import { announcementsApi } from '../../lib/announcements';
import { errorMessage } from '../../lib/enrollment';

const SCOPES = [
  { value: 'faculty', label: 'Whole faculty', identity: 'faculty' },
  { value: 'department', label: 'My department', identity: 'department' },
  { value: 'course', label: 'A course' },
];

/**
 * Posts to the real announcements endpoint.
 *
 * It used to write into the client-side mock store with a hardcoded author
 * name, and it expected `onClose`/`onSuccess` while its caller passes
 * `onCancel`/`onSaved`, so submitting called an undefined function and threw.
 */
const AnnouncementForm = ({ onCancel, onSaved, courses = [], user }) => {
  const availableScopes = SCOPES.filter((item) => item.value === 'course' || user?.[item.identity]);
  const [form, setForm] = useState({
    title: '',
    body: '',
    scope: availableScopes[0]?.value || 'course',
    course: '',
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
        body: form.body.trim(),
        scope: form.scope,
        published: true,
      };
      if (form.scope === 'course') {
        if (!form.course) {
          setError('Choose the course this announcement is for.');
          setBusy(false);
          return;
        }
        payload.scope_id = form.course;
      } else {
        payload.scope_id = user?.[form.scope];
      }
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
          value={form.body}
          onChange={(e) => setForm({ ...form, body: e.target.value })}
          rows={4}
          required
          className="w-full px-4 py-2 fet-input resize-none"
        />
      </div>

      <div>
        <label className="fet-label">Audience</label>
        <select
          className="w-full px-4 py-2 fet-select"
          value={form.scope}
          onChange={(e) => setForm({ ...form, scope: e.target.value, course: '' })}
        >
          {availableScopes.map((s) => <option key={s.value} value={s.value}>{s.label}</option>)}
        </select>
      </div>

      {form.scope === 'course' ? (
        <div>
          <label className="fet-label">Course</label>
          <select
            className="w-full px-4 py-2 fet-select"
            value={form.course}
            onChange={(e) => setForm({ ...form, course: e.target.value })}
          >
            <option value="">Choose a course...</option>
            {courses.map((c) => (
              <option key={c.id} value={c.course}>
                {c.course_code} — {c.course_title}
              </option>
            ))}
          </select>
          <p className="text-[11.5px] text-text-tertiary mt-1">
            Course announcements can only be posted by the lecturer who teaches that course.
          </p>
        </div>
      ) : null}

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
