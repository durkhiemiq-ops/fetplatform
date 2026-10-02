import React, { useState, useEffect, useCallback } from 'react';
import { Crown, Loader2, AlertCircle, X, UserCheck } from 'lucide-react';
import { projectsApi } from '../../lib/projects';

/**
 * Appoint the single class delegate for a course offering. The delegate can
 * form and manage groups inside a class-wide project.
 */
const ClassDelegateControl = ({ offeringId, canAppoint }) => {
  const [delegate, setDelegate] = useState(null);
  const [candidates, setCandidates] = useState([]);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState('');
  const [showPicker, setShowPicker] = useState(false);
  const [search, setSearch] = useState('');

  const load = useCallback(async () => {
    if (!offeringId) { setLoading(false); return; }
    setLoading(true);
    setError('');
    try {
      const d = await projectsApi.getDelegate(offeringId);
      setDelegate(d && d.student ? d : null);
    } catch (err) {
      if (err.response?.status !== 403) {
        setError(err.response?.data?.error?.message || 'Could not load the class delegate.');
      }
    } finally {
      setLoading(false);
    }
  }, [offeringId]);

  useEffect(() => { load(); }, [load]);

  const openPicker = async () => {
    setShowPicker(true);
    setSearch('');
    try {
      const c = await projectsApi.delegateCandidates(offeringId);
      setCandidates(Array.isArray(c) ? c : []);
    } catch (err) {
      setError(err.response?.data?.error?.message || 'Could not load students.');
    }
  };

  const appoint = async (studentId) => {
    setSaving(true);
    setError('');
    try {
      await projectsApi.appointDelegate(offeringId, studentId);
      setShowPicker(false);
      await load();
    } catch (err) {
      setError(err.response?.data?.error?.message || 'Could not appoint the delegate.');
    } finally {
      setSaving(false);
    }
  };

  const clear = async () => {
    if (!window.confirm('Remove the class delegate? Nobody will be able to form groups on your behalf.')) return;
    setSaving(true);
    setError('');
    try {
      await projectsApi.removeDelegate(offeringId);
      await load();
    } catch (err) {
      setError(err.response?.data?.error?.message || 'Could not remove the delegate.');
    } finally {
      setSaving(false);
    }
  };

  if (!offeringId || loading) return null;

  const term = search.trim().toLowerCase();
  const visible = candidates.filter((c) => (
    !term
    || (c.full_name || '').toLowerCase().includes(term)
    || (c.student_number || '').toLowerCase().includes(term)
  ));

  return (
    <div className="rounded-xl border border-border-default bg-white p-4">
      <div className="flex items-center justify-between gap-2 flex-wrap">
        <div className="min-w-0">
          <p className="text-sm font-medium text-text-primary flex items-center gap-2">
            <Crown size={15} className="text-amber-500" /> Class delegate
          </p>
          {delegate ? (
            <p className="text-xs text-text-secondary mt-0.5">
              {delegate.student_name}
              {delegate.student_number ? ` · ${delegate.student_number}` : ''}
              {delegate.is_delegate ? ' (you)' : ''}
            </p>
          ) : (
            <p className="text-xs text-text-secondary mt-0.5">
              Nobody appointed. Without a delegate you are the only one who can form groups.
            </p>
          )}
        </div>
        {canAppoint && (
          <div className="flex items-center gap-2">
            <button onClick={openPicker} className="fet-btn-secondary text-xs">
              <UserCheck size={14} />
              {delegate ? 'Change' : 'Appoint'}
            </button>
            {delegate && (
              <button
                onClick={clear}
                disabled={saving}
                className="p-1.5 rounded-lg text-text-secondary hover:text-danger hover:bg-red-50"
                title="Remove delegate"
              >
                <X size={15} />
              </button>
            )}
          </div>
        )}
      </div>

      {error && (
        <p className="text-xs text-red-600 mt-2 flex items-start gap-1">
          <AlertCircle size={12} className="mt-0.5 shrink-0" /> {error}
        </p>
      )}

      {showPicker && (
        <div className="mt-3 pt-3 border-t border-border-default">
          <div className="relative mb-2">
            <input
              autoFocus
              value={search}
              onChange={(e) => setSearch(e.target.value)}
              placeholder="Search by name or matricule..."
              className="fet-input text-sm"
            />
          </div>
          {saving && <Loader2 size={14} className="animate-spin text-text-secondary" />}
          <div className="max-h-48 overflow-y-auto space-y-1">
            {visible.map((c) => (
              <button
                key={c.id}
                onClick={() => appoint(c.id)}
                disabled={saving}
                className="w-full text-left flex items-center justify-between gap-2 p-2 rounded-lg border border-border-default hover:border-primary text-sm disabled:opacity-50"
              >
                <span className="truncate">{c.full_name}</span>
                <span className="text-xs text-text-secondary shrink-0">{c.student_number}</span>
              </button>
            ))}
            {visible.length === 0 && (
              <p className="text-xs text-text-secondary text-center py-3">No student matches that search.</p>
            )}
          </div>
        </div>
      )}
    </div>
  );
};

export default ClassDelegateControl;
