import React, { useState } from 'react';
import { Check, Pencil, X } from 'lucide-react';
import { submitCorrection } from '../../api/attendance';

/**
 * AttendanceTable — renders backend attendance records and lets lecturers
 * append an audited correction. The backend never overwrites the original
 * record; it only appends a correction event (BR-042).
 */
const AttendanceTable = ({ records, empty = 'No attendance records for this session.', canCorrect, onCorrected }) => {
  const [correctingId, setCorrectingId] = useState(null);
  const [reason, setReason] = useState('');
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');

  if (!records || records.length === 0) {
    return <div className="text-center py-8 text-text-secondary">{empty}</div>;
  }

  const fmt = (v) => {
    if (!v) return '—';
    const d = new Date(v);
    return Number.isNaN(d.getTime()) ? String(v) : d.toLocaleString();
  };

  const handleSubmit = async (recordId) => {
    if (!reason.trim() || busy) return;
    setBusy(true);
    setError('');
    try {
      await submitCorrection(recordId, reason.trim());
      setCorrectingId(null);
      setReason('');
      onCorrected && onCorrected();
    } catch (err) {
      setError(err.message || 'Could not save the correction.');
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="overflow-x-auto">
      <table className="fet-table">
        <thead>
          <tr>
            <th>Student</th>
            <th>Course</th>
            <th>Time</th>
            <th>Status</th>
            <th>Corrections</th>
            {canCorrect && <th />}
          </tr>
        </thead>
        <tbody>
          {records.map((record) => (
            <React.Fragment key={record.id}>
              <tr>
                <td className="font-medium">{record.student_name || record.studentName || record.studentId || '—'}</td>
                <td className="text-sm">{record.course_code || record.courseCode || '—'}</td>
                <td className="text-sm">{fmt(record.recorded_at || record.time)}</td>
                <td>
                  <span className={`fet-badge ${record.corrected || record.corrections?.length ? 'fet-badge-warning' : 'fet-badge-present'}`}>
                    {record.corrected || record.corrections?.length ? 'Corrected' : (record.status || 'PRESENT')}
                  </span>
                </td>
                <td className="text-sm">
                  {record.correction_count || record.corrections?.length ? (
                    <span className="inline-flex items-center gap-1 text-[#B45309] font-medium">
                      <Pencil size={13} /> {record.correction_count ?? record.corrections.length}
                    </span>
                  ) : (
                    <span className="text-text-secondary">—</span>
                  )}
                </td>
                {canCorrect && (
                  <td className="text-right">
                    {correctingId === record.id ? (
                      <button
                        type="button"
                        onClick={() => { setCorrectingId(null); setReason(''); setError(''); }}
                        className="inline-flex items-center gap-1 text-sm text-text-secondary"
                      >
                        <X size={14} /> Cancel
                      </button>
                    ) : (
                      <button
                        type="button"
                        onClick={() => setCorrectingId(record.id)}
                        className="inline-flex items-center gap-1 text-sm text-primary hover:underline"
                      >
                        <Pencil size={13} /> Correct
                      </button>
                    )}
                  </td>
                )}
              </tr>
              {correctingId === record.id && (
                <tr>
                  <td colSpan={canCorrect ? 6 : 5} className="bg-page-bg">
                    <div className="flex flex-col gap-2 py-1 sm:flex-row sm:items-start">
                      <input
                        type="text"
                        value={reason}
                        onChange={(e) => setReason(e.target.value)}
                        placeholder="Reason for the correction (required — recorded for the audit trail)"
                        className="fet-input flex-1"
                      />
                      <button
                        type="button"
                        disabled={busy || !reason.trim()}
                        onClick={() => handleSubmit(record.id)}
                        className="inline-flex items-center gap-2 rounded-lg bg-primary px-3 py-2 text-sm font-medium text-white hover:bg-primary-dark disabled:opacity-50"
                      >
                        <Check size={14} /> {busy ? 'Saving…' : 'Save correction'}
                      </button>
                    </div>
                    {error && <p className="pt-1 text-sm text-danger">{error}</p>}
                  </td>
                </tr>
              )}
            </React.Fragment>
          ))}
        </tbody>
      </table>
    </div>
  );
};

export default AttendanceTable;
