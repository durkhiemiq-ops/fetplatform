import React, { useCallback, useEffect, useState } from 'react';
import { UserCheck, ShieldCheck, RefreshCw, AlertCircle, CheckCircle2 } from 'lucide-react';
import { SectionHeader, Card, CardBody, Callout, DataTable, Pill, EmptyState } from '../UI';
import { lecturerApprovalApi } from '../../lib/auth';
import { errorMessage } from '../../lib/enrollment';

/**
 * Administrator approval queue for lecturer applications.
 *
 * A self-registered lecturer is stored PENDING and holds no academic
 * privileges until an administrator decides. This screen is the human side of
 * `POST /accounts/lecturers/<id>/approval/`; the server re-checks the
 * administrator role and writes an audit entry either way, so this component
 * is a convenience, never the enforcement point.
 *
 * Password material is never fetched or displayed — UserSerializer does not
 * serialise it.
 */

const toneFor = (status) => {
  switch (status) {
    case 'PENDING':
      return 'wn';
    case 'APPROVED':
      return 'ok';
    case 'REJECTED':
      return 'bd';
    default:
      return 'in';
  }
};

const labelFor = (status) => {
  switch (status) {
    case 'PENDING':
      return 'Pending review';
    case 'APPROVED':
      return 'Approved';
    case 'REJECTED':
      return 'Rejected';
    default:
      return 'Not an applicant';
  }
};

const LecturerApprovals = () => {
  const [rows, setRows] = useState([]);
  const [loading, setLoading] = useState(true);
  const [busyId, setBusyId] = useState(null);
  const [error, setError] = useState('');
  const [flash, setFlash] = useState('');

  const load = useCallback(async () => {
    setLoading(true);
    setError('');
    try {
      setRows(await lecturerApprovalApi.list());
    } catch (err) {
      setError(errorMessage(err, 'Could not load lecturers.'));
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  const decide = async (user, decision) => {
    setBusyId(user.id);
    setError('');
    setFlash('');
    try {
      await lecturerApprovalApi.decide(user.id, decision);
      setFlash(
        decision === 'approve'
          ? `${user.first_name} ${user.last_name} approved.`
          : `${user.first_name} ${user.last_name} rejected.`
      );
      await load();
    } catch (err) {
      setError(errorMessage(err, 'Could not record the decision.'));
    } finally {
      setBusyId(null);
    }
  };

  const pending = rows.filter((r) => r.lecturer_approval_status === 'PENDING').length;

  const columns = [
    {
      key: 'name',
      label: 'Lecturer',
      render: (r) => (
        <div>
          <div className="font-semibold text-text-primary">
            {r.first_name} {r.last_name}
          </div>
          <div className="text-xs text-text-secondary">{r.email}</div>
        </div>
      ),
    },
    {
      key: 'staffid',
      label: 'Staff no.',
      width: '130px',
      render: (r) => r.staffid || <span className="text-text-tertiary">—</span>,
    },
    {
      key: 'department',
      label: 'Department',
      width: '160px',
      render: (r) => r.department?.name || <span className="text-text-tertiary">—</span>,
    },
    {
      key: 'lecturer_approval_status',
      label: 'Status',
      width: '170px',
      render: (r) => (
        <Pill tone={toneFor(r.lecturer_approval_status)}>
          {labelFor(r.lecturer_approval_status)}
        </Pill>
      ),
    },
    {
      key: 'actions',
      label: 'Decision',
      width: '210px',
      align: 'right',
      render: (r) =>
        // Only an actual applicant is decidable. A NULL status is a
        // pre-existing lecturer, not an undecided application.
        r.lecturer_approval_status ? (
          <div className="flex justify-end gap-2">
            <button
              type="button"
              className="fet-btn-secondary text-[12px]"
              disabled={busyId === r.id}
              onClick={() => decide(r, 'reject')}
            >
              Reject
            </button>
            <button
              type="button"
              className="fet-btn-primary text-[12px]"
              disabled={busyId === r.id}
              onClick={() => decide(r, 'approve')}
            >
              {busyId === r.id ? 'Saving…' : 'Approve'}
            </button>
          </div>
        ) : (
          <span className="text-xs text-text-tertiary">—</span>
        ),
    },
  ];

  return (
    <div className="space-y-5">
      <SectionHeader
        icon={UserCheck}
        title="Lecturer approvals"
        subtitle={
          pending > 0
            ? `${pending} application${pending === 1 ? '' : 's'} awaiting a decision.`
            : 'No lecturer applications are awaiting a decision.'
        }
        actions={
          <button type="button" className="fet-btn-secondary text-[12px]" onClick={load} disabled={loading}>
            <RefreshCw size={14} />
            {loading ? 'Refreshing…' : 'Refresh'}
          </button>
        }
      />

      {flash ? <Callout tone="ok" icon={CheckCircle2}>{flash}</Callout> : null}
      {error ? <Callout tone="bd" icon={AlertCircle}>{error}</Callout> : null}

      <Callout tone="in">
        Self-registered lecturers are held as <strong>Pending</strong> and cannot act as
        teaching staff until approved. A lecturer with no application on record is a
        pre-existing account and needs no decision here.
      </Callout>

      <Card>
        <CardBody>
          <DataTable
            columns={columns}
            rows={rows}
            empty={
              <EmptyState
                icon={ShieldCheck}
                title={loading ? 'Loading lecturers…' : 'No lecturer accounts'}
                subtitle="Lecturers created through self-registration appear here for approval."
              />
            }
          />
        </CardBody>
      </Card>
    </div>
  );
};

export default LecturerApprovals;
