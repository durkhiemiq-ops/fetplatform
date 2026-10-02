import React, { useState } from 'react';
import { KeyRound, ShieldCheck } from 'lucide-react';
import { useNavigate } from 'react-router-dom';
import { SectionHeader, Card, CardBody, CardFoot, Callout } from '../UI';
import { authApi } from '../../lib/auth';
import { errorMessage } from '../../lib/enrollment';

const RULES = [
  'At least 8 characters.',
  'Different from the password you are replacing.',
  'Given to you once by an administrator, never reused.',
];

const ChangePassword = ({ user, forced = false }) => {
  const navigate = useNavigate();
  const [form, setForm] = useState({ current: '', next: '', confirm: '' });
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const [done, setDone] = useState(false);

  const submit = async (e) => {
    e.preventDefault();
    setError('');

    // The server enforces all of this too, but a roster student typing a short
    // password should not have to round-trip to find out.
    if (form.next.length < 8) { setError('New password must be at least 8 characters.'); return; }
    if (form.next === form.current) { setError('New password must be different from the current one.'); return; }
    if (form.next !== form.confirm) { setError('The two new passwords do not match.'); return; }

    setBusy(true);
    try {
      await authApi.changePassword({
        current_password: form.current,
        new_password: form.next,
      });
      setDone(true);
      setForm({ current: '', next: '', confirm: '' });
      // Keep the cached user snapshot fresh. There is no server-side
      // forced-change flag today (see the removal note in App.jsx), so this is
      // purely to avoid a stale display name/role after the change.
      try {
        const me = await authApi.me();
        const body = me?.data?.data ?? me?.data;
        localStorage.setItem('fet_user', JSON.stringify(body));
      } catch { /* the reload below re-reads it anyway */ }
    } catch (err) {
      setError(errorMessage(err, 'Could not change your password.'));
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="space-y-5 max-w-2xl">
      <SectionHeader
        area="hub"
        icon={KeyRound}
        title="Change password"
        subtitle={forced
          ? 'Your account was created from the student roster with a temporary password. Choose your own to continue.'
          : 'Update the password you sign in with.'}
      />

      {forced ? (
        <Callout tone="warn">
          You cannot use the rest of the platform until you set a new password.
        </Callout>
      ) : null}

      {done ? (
        <Callout tone="ok" icon={ShieldCheck}>
          Password changed.
          {!forced ? ' You can carry on as normal.' : null}
        </Callout>
      ) : null}

      {error ? <Callout tone="bad">{error}</Callout> : null}

      <Card accent="hub">
        <CardBody>
          <form onSubmit={submit} className="space-y-4">
            <div>
              <label className="fet-label">Current password</label>
              <input
                type="password"
                className="fet-input"
                autoComplete="current-password"
                value={form.current}
                onChange={(e) => setForm({ ...form, current: e.target.value })}
                required
              />
            </div>
            <div>
              <label className="fet-label">New password</label>
              <input
                type="password"
                className="fet-input"
                autoComplete="new-password"
                value={form.next}
                onChange={(e) => setForm({ ...form, next: e.target.value })}
                required
              />
            </div>
            <div>
              <label className="fet-label">Confirm new password</label>
              <input
                type="password"
                className="fet-input"
                autoComplete="new-password"
                value={form.confirm}
                onChange={(e) => setForm({ ...form, confirm: e.target.value })}
                required
              />
            </div>
            <ul className="text-[12px] text-text-tertiary space-y-1">
              {RULES.map((r) => <li key={r}>• {r}</li>)}
            </ul>
          </form>
        </CardBody>
        <CardFoot>
          <div className="flex items-center justify-end gap-3">
            {!forced ? (
              <button type="button" onClick={() => navigate(-1)} className="fet-btn-secondary">
                Cancel
              </button>
            ) : null}
            <button
              type="button"
              onClick={submit}
              disabled={busy}
              className="fet-btn-primary"
            >
              {busy ? 'Saving...' : 'Change password'}
            </button>
          </div>
        </CardFoot>
      </Card>
    </div>
  );
};

export default ChangePassword;
