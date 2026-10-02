import React, { useState, useEffect, useCallback } from 'react';
import { FilePlus2, Check, X, RefreshCw } from 'lucide-react';
import {
  SectionHeader, Card, CardBody, CardHead, DataTable, Pill, Callout,
  EmptyState, Avatar,
} from '../UI';
import { enrollmentApi, errorMessage } from '../../lib/enrollment';
import { learningApi } from '../../lib/learning';
import { normalizeRole } from '../../lib/profile';
import { formatDate } from '../../lib/format';

const STATUS_TONE = { PENDING: 'warn', APPROVED: 'ok', REJECTED: 'bad' };

const ApplyForm = ({ offerings, enrolledIds, onDone }) => {
  const [offeringId, setOfferingId] = useState('');
  const [reason, setReason] = useState('');
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');

  const choices = offerings.filter((o) => !enrolledIds.has(o.id));

  const submit = async (e) => {
    e.preventDefault();
    setBusy(true);
    setError('');
    try {
      await enrollmentApi.applyCarryOver(offeringId, reason.trim());
      setOfferingId('');
      setReason('');
      await onDone();
    } catch (err) {
      setError(errorMessage(err, 'Could not submit that application.'));
    } finally {
      setBusy(false);
    }
  };

  return (
    <form onSubmit={submit} className="space-y-3">
      {error ? <Callout tone="bad">{error}</Callout> : null}
      <div>
        <label className="fet-label">Course</label>
        <select className="fet-select" value={offeringId} onChange={(e) => setOfferingId(e.target.value)} required>
          <option value="">Choose a course...</option>
          {choices.map((o) => (
            <option key={o.id} value={o.id}>
              {o.course_code} — {o.course_title}
            </option>
          ))}
        </select>
      </div>
      <div>
        <label className="fet-label">Reason</label>
        <textarea
          className="fet-input resize-none"
          rows={3}
          value={reason}
          onChange={(e) => setReason(e.target.value)}
          placeholder="e.g. I failed CSC301 last semester and need to repeat it."
        />
      </div>
      <div className="flex justify-end">
        <button type="submit" className="fet-btn-primary" disabled={busy || !offeringId}>
          {busy ? 'Submitting...' : 'Apply'}
        </button>
      </div>
    </form>
  );
};

const CarryOverPage = ({ user }) => {
  const isStudent = normalizeRole(user?.role) === 'student';
  const [rows, setRows] = useState([]);
  const [offerings, setOfferings] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [notice, setNotice] = useState('');
  const [showApply, setShowApply] = useState(false);
  const [filter, setFilter] = useState('');
  const [notes, setNotes] = useState({});
  const [busy, setBusy] = useState('');

  const load = useCallback(async () => {
    setLoading(true);
    setError('');
    try {
      const [list, offers] = await Promise.all([
        enrollmentApi.listCarryOver(filter || undefined),
        isStudent ? learningApi.getAllCourses() : Promise.resolve([]),
      ]);
      setRows(list || []);
      setOfferings(offers || []);
    } catch (err) {
      setError(errorMessage(err, 'Could not load carry-over applications.'));
    } finally {
      setLoading(false);
    }
  }, [filter, isStudent]);

  useEffect(() => { load(); }, [load]);

  const review = async (id, decision) => {
    setBusy(id);
    setError('');
    setNotice('');
    try {
      const res = await enrollmentApi.reviewCarryOver(id, decision, notes[id] || '');
      setNotice(decision === 'APPROVED'
        ? 'Approved — the student is now enrolled.'
        : 'Application rejected.');
      if (decision === 'APPROVED' && res?.enrolled) setNotice('Approved — the student is now enrolled.');
      await load();
    } catch (err) {
      setError(errorMessage(err, 'Could not record that decision.'));
    } finally {
      setBusy('');
    }
  };

  const enrolledIds = new Set(
    rows.filter((r) => r.status === 'APPROVED').map((r) => r.course_offering_id)
  );

  const columns = [
    {
      key: 'student_name',
      label: 'Student',
      render: (r) => (isStudent ? null : (
        <div className="flex items-center gap-2">
          <Avatar name={r.student_name || '?'} size={28} />
          <div className="min-w-0">
            <p className="text-[13px] text-text-primary">{r.student_name}</p>
            <p className="text-[11.5px] text-text-tertiary num">{r.matricule || r.student_email}</p>
          </div>
        </div>
      )),
    },
    {
      key: 'course_title',
      label: 'Course',
      render: (r) => (
        <div>
          <p className="text-[13px] text-text-primary">
            <span className="num text-text-secondary">{r.course_code}</span> {r.course_title}
          </p>
          {r.reason ? <p className="text-[11.5px] text-text-tertiary mt-0.5">{r.reason}</p> : null}
        </div>
      ),
    },
    { key: 'created_at', label: 'Applied', width: '130px', render: (r) => formatDate(r.created_at) },
    {
      key: 'status',
      label: 'Status',
      width: '110px',
      render: (r) => <Pill tone={STATUS_TONE[r.status] || 'mute'}>{String(r.status).toLowerCase()}</Pill>,
    },
  ];

  if (!isStudent) {
    columns.splice(3, 0, {
      key: 'decision',
      label: 'Decision',
      width: '300px',
      render: (r) => (r.status !== 'PENDING' ? (
        <span className="text-[12px] text-text-tertiary">
          {r.review_note || 'Decided.'}
        </span>
      ) : (
        <div className="space-y-2">
          <input
            className="fet-input text-[12px]"
            placeholder="Note (optional)"
            value={notes[r.id] || ''}
            onChange={(e) => setNotes({ ...notes, [r.id]: e.target.value })}
          />
          <div className="flex gap-2">
            <button
              type="button"
              onClick={() => review(r.id, 'APPROVED')}
              disabled={busy === r.id}
              className="fet-btn-primary text-[12px]"
            >
              <Check size={13} /> Approve
            </button>
            <button
              type="button"
              onClick={() => review(r.id, 'REJECTED')}
              disabled={busy === r.id}
              className="fet-btn-secondary text-[12px]"
            >
              <X size={13} /> Reject
            </button>
          </div>
        </div>
      )),
    });
  }

  const pending = rows.filter((r) => r.status === 'PENDING').length;

  return (
    <div className="space-y-5">
      <SectionHeader
        area="classrooms"
        icon={FilePlus2}
        title="Carry-over"
        subtitle={isStudent
          ? 'Request to join a course you were not enrolled in — for example repeating one you failed.'
          : 'Approve or reject carry-over requests. Approval is what enrols the student, and only then can their attendance be confirmed.'}
        actions={(
          <>
            {isStudent ? (
              <button type="button" onClick={() => setShowApply((v) => !v)} className="fet-btn-primary">
                {showApply ? <X size={14} /> : <FilePlus2 size={14} />}
                {showApply ? 'Cancel' : 'New application'}
              </button>
            ) : null}
            <button type="button" onClick={load} className="fet-btn-secondary" disabled={loading}>
              <RefreshCw size={14} /> Refresh
            </button>
          </>
        )}
      />

      {error ? <Callout tone="bad">{error}</Callout> : null}
      {notice ? <Callout tone="ok">{notice}</Callout> : null}
      {!isStudent && pending > 0 ? (
        <Callout tone="warn">{pending} application{pending === 1 ? '' : 's'} waiting for a decision.</Callout>
      ) : null}

      {isStudent && showApply ? (
        <Card accent="classrooms">
          <CardHead title="New carry-over application" square="classrooms" />
          <CardBody>
            {offerings.length === 0 ? (
              <p className="text-text-secondary text-[13px]">
                No course offerings are available to apply for yet.
              </p>
            ) : (
              <ApplyForm offerings={offerings} enrolledIds={enrolledIds} onDone={load} />
            )}
          </CardBody>
        </Card>
      ) : null}

      <Card accent="classrooms">
        <CardHead title={isStudent ? 'My applications' : 'All applications'} square="classrooms">
          <div className="ui-tabs" style={{ border: 'none', padding: 0 }}>
            {[
              { key: '', label: 'All' },
              { key: 'PENDING', label: 'Pending' },
              { key: 'APPROVED', label: 'Approved' },
              { key: 'REJECTED', label: 'Rejected' },
            ].map((t) => (
              <button
                key={t.key || 'all'}
                type="button"
                className={`ui-tab${filter === t.key ? ' active' : ''}`}
                onClick={() => setFilter(t.key)}
              >
                {t.label}
              </button>
            ))}
          </div>
        </CardHead>
        <CardBody>
          <DataTable
            columns={columns}
            rows={rows}
            empty={loading
              ? <p className="text-text-secondary text-[13px] py-6 text-center">Loading applications...</p>
              : <EmptyState
                  icon={FilePlus2}
                  title={isStudent ? 'No applications' : 'Nothing to review'}
                  subtitle={isStudent
                    ? 'If you need a course you are not registered for, apply for carry-over.'
                    : 'Carry-over applications from students will appear here.'}
                />}
          />
        </CardBody>
      </Card>
    </div>
  );
};

export default CarryOverPage;
