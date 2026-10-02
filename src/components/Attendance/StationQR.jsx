import React, { useEffect, useMemo, useState } from 'react';
import QRCode from 'qrcode';
import { Check, Clock, QrCode, Save, Users } from 'lucide-react';
import { issueCheckpointToken, selectCheckpoints } from '../../api/attendance';

/**
 * StationQR — the lecturer's live check-in screen.
 *
 * Confirms which enrolled students become checkpoints and then projects one
 * checkpoint's QR at a time. Each QR encodes a fresh token issued just-in-time
 * (10s TTL, single-use, bound to that student — BR-039/061). A screenshot of
 * an expired code cannot be re-used.
 */
const StationQR = ({ session, onRefresh }) => {
  const checkpoints = session.checkpoints || [];
  const eligible = session.eligible_students || [];
  const isActive = session.status === 'ACTIVE';

  const [selectedIds, setSelectedIds] = useState(() => checkpoints.map((c) => c.student));
  const [saving, setSaving] = useState(false);
  const [selectedCheckpointId, setSelectedCheckpointId] = useState(null);
  const [token, setToken] = useState(null);
  const [countdown, setCountdown] = useState(0);
  const [qrUrl, setQrUrl] = useState(null);
  const [error, setError] = useState('');

  useEffect(() => {
    setSelectedIds(checkpoints.map((c) => c.student));
  }, [session.id, checkpoints.length]);

  useEffect(() => {
    const first = checkpoints[0];
    setSelectedCheckpointId((prev) =>
      prev && checkpoints.some((c) => c.id === prev) ? prev : first?.id || null
    );
  }, [session.id, checkpoints]);

  const currentCheckpoint = useMemo(
    () => checkpoints.find((c) => c.id === selectedCheckpointId) || null,
    [checkpoints, selectedCheckpointId]
  );

  // Auto-rotate tokens: issue just-in-time, countdown, re-issue on expiry.
  useEffect(() => {
    if (!currentCheckpoint || !isActive) {
      setQrUrl(null);
      setToken(null);
      setError('');
      return undefined;
    }
    let stopped = false;
    let issuing = false;
    let remaining = 0;

    const issue = async () => {
      try {
        const data = await issueCheckpointToken(currentCheckpoint.id);
        if (stopped) return;
        const ttl = data.ttl_seconds || 10;
        remaining = ttl;
        setToken(data.token);
        setCountdown(ttl);
        const url = await QRCode.toDataURL(data.token, { width: 320, margin: 1 });
        if (!stopped) setQrUrl(url);
        setError('');
      } catch (err) {
        if (!stopped) {
          setError(err.message || 'Could not generate a QR code.');
          setQrUrl(null);
        }
      }
    };

    issuing = true;
    issue().finally(() => { issuing = false; });
    const tick = setInterval(() => {
      remaining -= 1;
      if (remaining <= 0 && !issuing) {
        issuing = true;
        issue().finally(() => { issuing = false; });
      } else {
        setCountdown(Math.max(0, remaining));
      }
    }, 1000);

    return () => {
      stopped = true;
      clearInterval(tick);
    };
  }, [currentCheckpoint?.id, isActive]);

  const toggleStudent = (id) => {
    setSelectedIds((prev) =>
      prev.includes(id) ? prev.filter((x) => x !== id) : [...prev, id]
    );
  };

  const handleSave = async () => {
    if (selectedIds.length === 0 || saving) return;
    setSaving(true);
    setError('');
    try {
      await selectCheckpoints(session.id, selectedIds);
      onRefresh && onRefresh();
    } catch (err) {
      setError(err.message || 'Could not save checkpoints.');
    } finally {
      setSaving(false);
    }
  };

  return (
    <div className="space-y-5">
      <div>
        <h3 className="mb-2 flex items-center gap-2 text-sm font-semibold text-text-primary">
          <Users size={16} /> Confirm checkpoint students
        </h3>
        <p className="mb-3 text-xs text-text-secondary">
          Select the students to include as checkpoints. Each gets their own rotating QR (single-use).
        </p>
        {eligible.length === 0 ? (
          <p className="text-xs text-text-secondary">No enrolled students found for this class yet.</p>
        ) : (
          <div className="space-y-2">
            <div className="grid grid-cols-1 gap-2 sm:grid-cols-2 lg:grid-cols-3">
              {eligible.map((student) => {
                const checked = selectedIds.includes(student.id);
                return (
                  <label
                    key={student.id}
                    className={`flex cursor-pointer items-center gap-2 rounded-lg border px-3 py-2 text-sm transition-colors ${
                      checked
                        ? 'border-primary bg-primary-light/40 text-text-primary'
                        : 'border-border-default bg-white text-text-secondary hover:border-primary/40'
                    }`}
                  >
                    <input
                      type="checkbox"
                      checked={checked}
                      onChange={() => toggleStudent(student.id)}
                      className="accent-primary"
                    />
                    <span className="font-medium">
                      {student.first_name} {student.last_name}
                    </span>
                    <span className="ml-auto text-xs opacity-60">#{String(student.username).slice(-4)}</span>
                  </label>
                );
              })}
            </div>
            <button
              type="button"
              disabled={saving || selectedIds.length === 0}
              onClick={handleSave}
              className="inline-flex items-center gap-2 rounded-lg border border-primary px-3 py-2 text-sm font-medium text-primary hover:bg-primary-light/40 disabled:opacity-50"
            >
              <Save size={15} /> {saving ? 'Saving…' : `Save ${selectedIds.length} checkpoints`}
            </button>
          </div>
        )}
      </div>

      {checkpoints.length > 0 && (
        <div className="rounded-xl bg-gradient-to-r from-[#0F0B3D] to-[#3F35B5] p-5 text-white">
          <div className="mb-3 flex flex-wrap items-center justify-between gap-3">
            <div className="flex items-center gap-2">
              <QrCode size={18} />
              <span className="font-semibold">CHECK-IN QR</span>
            </div>
            <div className="flex items-center gap-2 text-xs">
              {isActive ? (
                <span className="flex items-center gap-1 rounded-full bg-white/15 px-3 py-1">
                  <Clock size={13} /> Rotates every {countdown}s
                </span>
              ) : (
                <span className="rounded-full bg-white/15 px-3 py-1">Session not active</span>
              )}
            </div>
          </div>

          <div className="mb-4 flex flex-wrap gap-2">
            <select
              value={selectedCheckpointId || ''}
              onChange={(e) => setSelectedCheckpointId(e.target.value)}
              className="rounded-lg border border-white/20 bg-white/10 px-3 py-2 text-sm text-white outline-none [&>option]:text-[#0F0B3D]"
              disabled={!isActive}
            >
              {checkpoints.map((c) => (
                <option key={c.id} value={c.id}>
                  {c.student_name}
                  {c.marked ? ' ✓ marked' : ''}
                </option>
              ))}
            </select>
            <span className="rounded-full bg-white/15 px-3 py-2 text-xs">
              {checkpoints.filter((c) => c.marked).length}/{checkpoints.length} marked
            </span>
          </div>

          {currentCheckpoint ? (
            <div className="flex flex-col items-center gap-3">
              <p className="text-sm">
                <span className="font-bold">{currentCheckpoint.student_name}</span> — scan with the student's own device
              </p>
              {qrUrl ? (
                <img
                  src={qrUrl}
                  alt={`QR code for ${currentCheckpoint.student_name}`}
                  className="rounded-xl bg-white p-2"
                  width={220}
                  height={220}
                />
              ) : (
                <div className="flex h-[220px] w-[220px] items-center justify-center rounded-xl bg-white/10 text-center text-xs">
                  {isActive ? (error || 'Generating QR…') : 'Session inactive.'}
                </div>
              )}
              <div className="text-center text-xs opacity-80">
                {currentCheckpoint.marked ? (
                  <span className="flex items-center gap-1 font-semibold">
                    <Check size={14} /> Marked present
                  </span>
                ) : isActive ? (
                  'This code expires within seconds and works once.'
                ) : (
                  'Code is paused.'
                )}
              </div>
            </div>
          ) : (
            <p className="text-center text-sm opacity-80">Select a checkpoint to project its QR.</p>
          )}
        </div>
      )}

      {error && checkpoints.length === 0 && (
        <p className="text-sm text-danger">{error}</p>
      )}
    </div>
  );
};

export default StationQR;
