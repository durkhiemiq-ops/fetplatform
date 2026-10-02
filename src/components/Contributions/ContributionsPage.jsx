import React, { useState, useEffect, useCallback } from 'react';
import { Plus, Send, CheckCircle, XCircle, MessageSquare, FileText, Upload, AlertCircle } from 'lucide-react';
import ContributionForm from './ContributionForm';
import { useAppContext } from '../../context/AppContext';
import { getContributions, submitContribution, reviewContribution } from '../../api/projects';

/**
 * ContributionsPage — backed by the API.
 *
 * Previously loaded and saved contributions in localStorage, which meant a
 * reviewer's approval existed only in their own browser. BR-122/210: the
 * backend records every submission and every review, and a review is restricted
 * to the project's academics.
 */
const ContributionsPage = ({ user }) => {
  const { projects } = useAppContext();
  const [showForm, setShowForm] = useState(false);
  const [contributions, setContributions] = useState([]);
  const [filter, setFilter] = useState('all');
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [notice, setNotice] = useState('');

  const isLecturer = user?.role === 'lecturer' || user?.role === 'admin';

  const load = useCallback(async () => {
    setLoading(true);
    setError('');
    try {
      const rows = await getContributions();
      setContributions(Array.isArray(rows) ? rows : []);
    } catch (err) {
      setError(err.message || 'Could not load contributions.');
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  // Backend status vocabulary: pending_review | approved | rejected.
  const STATUS_LABELS = {
    pending_review: 'Pending Review',
    approved: 'Accepted',
    rejected: 'Rejected',
  };

  const myContributions = contributions.filter(
    (c) => c.student && c.student === user?.id
  );

  const handleNewContribution = async (data) => {
    setError('');
    try {
      await submitContribution(data.projectId || data.project, {
        evidence_type: 'task',
        evidence_ref: data.evidence_ref || data.taskId,
      });
      setShowForm(false);
      setNotice('Contribution submitted for review.');
      setTimeout(() => setNotice(''), 4000);
      await load();
    } catch (err) {
      setError(err.message || 'Could not submit the contribution.');
    }
  };

  const handleStatusChange = async (id, status) => {
    setError('');
    try {
      await reviewContribution(id, { approved: status === 'approved', notes: '' });
      await load();
    } catch (err) {
      setError(err.message || 'Could not record the review.');
    }
  };

  const getStatusColor = (status) => {
    switch (status) {
      case 'approved': return 'fet-badge fet-badge-active';
      case 'rejected': return 'fet-badge fet-badge-danger';
      case 'pending_review': return 'fet-badge fet-badge-pending';
      default: return 'fet-badge fet-badge-inactive';
    }
  };

  const displayed = isLecturer
    ? contributions.filter((c) => filter === 'all' || STATUS_LABELS[c.status] === filter)
    : myContributions;

  return (
    <div className="space-y-6">
      <div className="flex flex-col sm:flex-row items-start sm:items-center justify-between gap-4">
        <div>
          <h2 className="text-2xl font-bold text-text-primary">Contributions</h2>
          <p className="text-text-secondary" style={{ fontSize: '13px' }}>
            {isLecturer ? 'Review student contributions for your projects' : 'Track and submit your contributions'}
          </p>
        </div>
        {!isLecturer && (
          <button
            onClick={() => setShowForm(true)}
            className="fet-btn-primary flex items-center gap-2"
          >
            <Plus size={18} />
            Submit Contribution
          </button>
        )}
      </div>

      {isLecturer && (
        <div className="flex gap-2 flex-wrap">
          {['all', 'Pending Review', 'Accepted', 'Rejected'].map((s) => (
            <button
              key={s}
              onClick={() => setFilter(s)}
              className={`px-4 py-2 rounded-xl text-sm font-medium transition-colors ${
                filter === s ? 'fet-btn-primary' : 'fet-btn-secondary'
              }`}
            >
              {s === 'all' ? 'All' : s}
            </button>
          ))}
        </div>
      )}

      {notice && (
        <div className="rounded-lg border border-green-200 bg-green-50 px-4 py-2.5 text-[13px] text-green-800">
          {notice}
        </div>
      )}
      {error && (
        <div className="flex items-center gap-2 rounded-lg border border-red-200 bg-red-50 px-4 py-2.5 text-[13px] text-red-700">
          <AlertCircle size={14} /> {error}
        </div>
      )}

      {loading ? (
        <p className="py-8 text-center text-sm text-text-secondary">Loading contributions…</p>
      ) : displayed.length > 0 ? (
        <div className="space-y-4">
          {displayed.map((c) => {
            const project = projects.find((p) => p.id === c.project);
            return (
              <div key={c.id} className="fet-card p-6">
                <div className="flex items-start justify-between gap-4">
                  <div className="flex-1">
                    <div className="flex items-center gap-3 flex-wrap">
                      <h3 className="font-semibold text-text-primary">
                        {project?.title || 'Project contribution'}
                      </h3>
                      <span className={getStatusColor(c.status)}>{STATUS_LABELS[c.status] || c.status}</span>
                    </div>
                    {c.student_name && (
                      <p className="text-sm text-text-secondary mt-1">Submitted by {c.student_name}</p>
                    )}
                    {c.notes && <p className="text-sm text-text-primary mt-2">{c.notes}</p>}
                    <p className="text-xs text-text-secondary mt-2">
                      {c.created_at ? new Date(c.created_at).toLocaleString() : ''}
                      {' • '}Evidence: {c.evidence_type} ({c.evidence_ref})
                    </p>
                    {c.reviewed_at && (
                      <p className="text-xs text-text-secondary mt-1">
                        Reviewed {new Date(c.reviewed_at).toLocaleString()}
                        {c.notes ? ` — ${c.notes}` : ''}
                      </p>
                    )}
                  </div>
                </div>

                {/* BR-122: review is approve/reject only and is audited. */}
                {isLecturer && c.status === 'pending_review' && (
                  <div className="mt-4 pt-4 border-t border-border-default flex gap-3">
                    <button
                      onClick={() => handleStatusChange(c.id, 'approved')}
                      className="fet-btn-success flex items-center gap-1 text-xs"
                    >
                      <CheckCircle size={14} /> Accept
                    </button>
                    <button
                      onClick={() => handleStatusChange(c.id, 'rejected')}
                      className="fet-btn-danger flex items-center gap-1 text-xs"
                    >
                      <XCircle size={14} /> Reject
                    </button>
                  </div>
                )}
              </div>
            );
          })}
        </div>
      ) : (
        <div className="text-center py-12 fet-card">
          <FileText size={48} className="mx-auto text-text-secondary opacity-50" />
          <p className="text-text-secondary mt-4">
            {isLecturer ? 'No contributions to review yet.' : 'No contributions yet. Submit your first contribution!'}
          </p>
          {!isLecturer && (
            <button
              onClick={() => setShowForm(true)}
              className="mt-4 fet-btn-primary inline-flex items-center gap-2"
            >
              <Upload size={16} /> Submit Contribution
            </button>
          )}
        </div>
      )}

      {showForm && (
        <div className="fixed inset-0 bg-black/50 flex items-center justify-center z-50 p-4">
          <ContributionForm
            projectId={projects[0]?.id}
            onSubmit={handleNewContribution}
            onClose={() => setShowForm(false)}
          />
        </div>
      )}
    </div>
  );
};

export default ContributionsPage;
