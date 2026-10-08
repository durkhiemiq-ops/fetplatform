import React, { useState } from 'react';
import { Clock, XCircle } from 'lucide-react';
import { authApi } from '../../lib/auth';

/**
 * Waiting screen for lecturer applicants without teaching authorization.
 *
 * Driven entirely by the server-owned `lecturer_approval_status` from
 * GET /auth/me/ (PENDING / REJECTED / APPROVED / null). It never reads a
 * role from browser storage and never grants anything: the backend predicate
 * `is_authorized_academic_user` remains the sole enforcement point. This is
 * a UX gate only, so a pending applicant sees a clear status instead of a
 * full dashboard whose every teaching call answers 403.
 *
 * - PENDING: application awaiting an administrator decision.
 * - REJECTED: application declined; contact administration.
 * Any other value (APPROVED / null) never renders here — App only mounts
 * this component for PENDING / REJECTED lecturers.
 */
const PendingApproval = ({ user, status, onSignOut, onUserChanged }) => {
  const [refreshing, setRefreshing] = useState(false);
  const [error, setError] = useState('');
  const rejected = status === 'REJECTED';
  const email = user?.email || '';
  const name = [user?.first_name, user?.last_name].filter(Boolean).join(' ') || email.split('@')[0] || 'Lecturer';

  const refresh = async () => {
    setRefreshing(true);
    setError('');
    try {
      const response = await authApi.me();
      const fresh = response.data?.data ?? response.data;
      onUserChanged(fresh);
    } catch {
      setError('Could not refresh your status. Please try again.');
    } finally {
      setRefreshing(false);
    }
  };

  return (
    <div className="min-h-screen flex items-center justify-center bg-page-bg p-6">
      <div className="fet-card p-6 md:p-8 w-full max-w-md space-y-5 text-center">
        <div className="w-14 h-14 rounded-2xl flex items-center justify-center mx-auto" style={{ backgroundColor: rejected ? 'rgba(200,60,60,0.12)' : 'rgba(63,53,181,0.12)' }}>
          {rejected ? <XCircle size={28} className="text-danger" /> : <Clock size={28} className="text-primary" />}
        </div>
        <div>
          <h1 className="text-xl font-bold">
            {rejected ? 'Application not approved' : 'Application under review'}
          </h1>
          <p className="text-[13px] text-text-secondary mt-1">{name}{email ? ` · ${email}` : ''}</p>
        </div>
        {rejected ? (
          <p className="text-sm text-text-secondary">
            Your lecturer application was not approved, so teaching access is
            unavailable. Please contact administration if you believe this is
            a mistake.
          </p>
        ) : (
          <p className="text-sm text-text-secondary">
            Your lecturer application is waiting for an administrator decision.
            Teaching features unlock automatically once it is approved — you
            can refresh this page to check.
          </p>
        )}
        {error && <p role="alert" className="text-danger text-sm">{error}</p>}
        <div className="space-y-3">
          {!rejected && (
            <button onClick={refresh} disabled={refreshing} className="fet-btn-primary w-full">
              {refreshing ? 'Checking...' : 'Refresh status'}
            </button>
          )}
          <button onClick={onSignOut} className="fet-btn-secondary w-full">Sign out</button>
        </div>
      </div>
    </div>
  );
};

export default PendingApproval;
