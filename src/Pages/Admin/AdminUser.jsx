import React, { useState, useMemo, useEffect, useCallback } from 'react';
import { Search, Shield, UserCog, X, Users, AlertCircle, CheckCircle } from 'lucide-react';
import { listUsers, changeRole } from '../../api/auth';

/**
 * AdminUser — real user directory backed by the API.
 *
 * L1: this previously fabricated the user list from `students`/`lecturers`
 * (the latter is always empty — the backend has no lecturer-list endpoint) and
 * invented an admin row. Role changes were never sent anywhere: there is no
 * endpoint call at all, and `updateStudent`/`addStudent` were canned rejects.
 *
 * The backend is the only source of truth:
 *  - GET  /accounts/         -> the full user list (admin only)
 *  - POST /accounts/change-role/ -> role change, admin only, audited (BR-002/210)
 * BR-002: a role change cannot be self-assigned; the backend rejects it and so
 * does this UI.
 */
const ROLES = [
  { value: 'STUDENT', label: 'Student' },
  { value: 'LECTURER', label: 'Lecturer' },
  { value: 'ADMINISTRATOR', label: 'Administrator' },
];

const AdminUsers = ({ user }) => {
  const [users, setUsers] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [notice, setNotice] = useState('');
  const [searchTerm, setSearchTerm] = useState('');
  const [filterRole, setFilterRole] = useState('all');
  const [editing, setEditing] = useState(null);
  const [newRole, setNewRole] = useState('STUDENT');
  const [busy, setBusy] = useState(false);

  const load = useCallback(async () => {
    setLoading(true);
    setError('');
    try {
      const rows = await listUsers();
      setUsers(Array.isArray(rows) ? rows : []);
    } catch (err) {
      setError(err.message || 'Could not load users.');
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  const filtered = useMemo(() => {
    const q = searchTerm.toLowerCase();
    return users.filter(
      (u) =>
        (filterRole === 'all' || u.role === filterRole) &&
        (!q ||
          `${u.first_name || ''} ${u.last_name || ''}`.toLowerCase().includes(q) ||
          (u.email || '').toLowerCase().includes(q) ||
          (u.username || '').toLowerCase().includes(q) ||
          (u.matricule || '').toLowerCase().includes(q) ||
          (u.staffid || '').toLowerCase().includes(q))
    );
  }, [users, searchTerm, filterRole]);

  const handleChangeRole = async () => {
    if (!editing) return;
    setBusy(true);
    setError('');
    try {
      await changeRole({ user_id: editing.id, new_role: newRole });
      setNotice(`Role updated to ${newRole} for ${editing.email}.`);
      setTimeout(() => setNotice(''), 4000);
      setEditing(null);
      await load();
    } catch (err) {
      setError(err.message || 'Could not change the role.');
    } finally {
      setBusy(false);
    }
  };

  const roleBadge = (role) => {
    switch (role) {
      case 'ADMINISTRATOR': return 'fet-badge-danger';
      case 'LECTURER': return 'fet-badge-info';
      default: return 'fet-badge-inactive';
    }
  };

  const name = (u) => `${u.first_name || ''} ${u.last_name || ''}`.trim() || u.username;

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h2 className="text-2xl font-bold text-text-primary">User Management</h2>
          <p className="text-text-secondary" style={{ fontSize: '14px' }}>
            View accounts and change roles. Role changes are audited.
          </p>
        </div>
        <span className="fet-badge fet-badge-info inline-flex items-center gap-1">
          <Users size={13} /> {users.length} accounts
        </span>
      </div>

      {notice && (
        <div className="flex items-center gap-2 rounded-lg border border-green-200 bg-green-50 px-4 py-2.5 text-[13px] text-green-800">
          <CheckCircle size={14} /> {notice}
        </div>
      )}
      {error && (
        <div className="flex items-center gap-2 rounded-lg border border-red-200 bg-red-50 px-4 py-2.5 text-[13px] text-red-700">
          <AlertCircle size={14} /> {error}
        </div>
      )}

      <div className="flex flex-col sm:flex-row gap-4">
        <div className="relative flex-1">
          <Search className="absolute left-3 top-1/2 transform -translate-y-1/2 text-text-secondary" size={18} />
          <input
            type="text"
            placeholder="Search by name, email, matricule or staff ID..."
            value={searchTerm}
            onChange={(e) => setSearchTerm(e.target.value)}
            className="w-full pl-10 pr-4 py-2 fet-input"
          />
        </div>
        <select value={filterRole} onChange={(e) => setFilterRole(e.target.value)} className="fet-select">
          <option value="all">All roles</option>
          {ROLES.map((r) => (
            <option key={r.value} value={r.value}>{r.label}</option>
          ))}
        </select>
      </div>

      <div className="fet-card overflow-hidden">
        {loading ? (
          <p className="py-8 text-center text-sm text-text-secondary">Loading accounts…</p>
        ) : filtered.length === 0 ? (
          <p className="py-8 text-center text-sm text-text-secondary">
            {users.length === 0 ? 'No accounts found.' : 'No accounts match your search.'}
          </p>
        ) : (
          <div className="overflow-x-auto">
            <table className="fet-table">
              <thead>
                <tr className="bg-page-bg border-b border-border-default">
                  <th className="text-left py-3 px-4 text-[13px] font-semibold text-text-secondary uppercase">Name</th>
                  <th className="text-left py-3 px-4 text-[13px] font-semibold text-text-secondary uppercase">Email</th>
                  <th className="text-left py-3 px-4 text-[13px] font-semibold text-text-secondary uppercase">Identifier</th>
                  <th className="text-left py-3 px-4 text-[13px] font-semibold text-text-secondary uppercase">Role</th>
                  <th className="text-left py-3 px-4 text-[13px] font-semibold text-text-secondary uppercase">Verified</th>
                  <th className="text-right py-3 px-4 text-[13px] font-semibold text-text-secondary uppercase">Action</th>
                </tr>
              </thead>
              <tbody>
                {filtered.map((u) => (
                  <tr key={u.id} className="border-b border-border-default hover:bg-page-bg transition-colors">
                    <td className="py-3 px-4 font-medium text-text-primary">{name(u)}</td>
                    <td className="py-3 px-4 text-text-secondary text-[13px]">{u.email}</td>
                    <td className="py-3 px-4 text-text-secondary text-[13px] font-mono">
                      {u.matricule || u.staffid || '—'}
                    </td>
                    <td className="py-3 px-4">
                      <span className={`fet-badge ${roleBadge(u.role)}`}>{u.role}</span>
                    </td>
                    <td className="py-3 px-4 text-[13px]">
                      {u.is_email_verified ? 'Yes' : 'No'}
                    </td>
                    <td className="py-3 px-4 text-right">
                      {/* BR-002: the backend forbids self-assignment; hide the
                          control for your own account rather than letting it 403. */}
                      {u.id === user?.id ? (
                        <span className="text-[12px] text-text-secondary">Your account</span>
                      ) : (
                        <button
                          onClick={() => { setEditing(u); setNewRole(u.role); }}
                          className="inline-flex items-center gap-1 text-[13px] text-primary hover:underline"
                        >
                          <UserCog size={14} /> Change role
                        </button>
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>

      {editing && (
        <div className="fixed inset-0 bg-black/50 flex items-center justify-center z-50 p-4">
          <div className="bg-white rounded-xl shadow-xl max-w-md w-full p-6">
            <div className="flex items-center justify-between mb-4">
              <h3 className="text-[15px] font-bold text-text-primary flex items-center gap-2">
                <Shield size={16} /> Change role
              </h3>
              <button onClick={() => setEditing(null)} className="p-1 hover:bg-page-bg rounded-lg" aria-label="Close">
                <X size={20} className="text-text-secondary" />
              </button>
            </div>

            <p className="text-[13px] text-text-secondary mb-4">
              {name(editing)} ({editing.email})
            </p>

            <div className="space-y-2 mb-6">
              {ROLES.map((r) => (
                <label
                  key={r.value}
                  className={`flex items-center gap-2 rounded-lg border px-3 py-2 text-sm cursor-pointer ${
                    newRole === r.value
                      ? 'border-primary bg-primary-light/40 text-text-primary'
                      : 'border-border-default bg-white text-text-secondary'
                  }`}
                >
                  <input
                    type="radio"
                    name="role"
                    checked={newRole === r.value}
                    onChange={() => setNewRole(r.value)}
                    className="accent-primary"
                  />
                  {r.label}
                </label>
              ))}
            </div>

            <div className="flex justify-end gap-3">
              <button onClick={() => setEditing(null)} className="fet-btn-secondary" disabled={busy}>
                Cancel
              </button>
              <button onClick={handleChangeRole} className="fet-btn-primary disabled:opacity-60" disabled={busy}>
                {busy ? 'Saving…' : 'Apply change'}
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
};

export default AdminUsers;
