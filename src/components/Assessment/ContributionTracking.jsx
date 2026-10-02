import React, { useState, useEffect, useCallback, useMemo } from 'react';
import { TrendingUp, Users, Filter, Search, AlertCircle, FolderKanban } from 'lucide-react';
import { projectsApi } from '../../lib/projects';
import { errorMessage } from '../../lib/enrollment';
import { formatDate } from '../../lib/format';

/**
 * Per-member contribution tracking for a project group.
 *
 * Every number here comes from the group report endpoint, which the backend
 * computes from real task and contribution rows. Previously this screen derived
 * its figures from the mock dataset in the client, so it showed the same
 * invented students and percentages to every lecturer.
 */
const ContributionTracking = () => {
  const [projects, setProjects] = useState([]);
  const [projectId, setProjectId] = useState('');
  const [groups, setGroups] = useState([]);
  const [groupId, setGroupId] = useState('');
  const [report, setReport] = useState(null);
  const [searchTerm, setSearchTerm] = useState('');
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');

  // Projects, then the groups inside the chosen project.
  useEffect(() => {
    let cancelled = false;
    (async () => {
      setLoading(true);
      setError('');
      try {
        const list = await projectsApi.listProjects();
        if (cancelled) return;
        setProjects(list || []);
        setProjectId((prev) => prev || (list?.[0]?.id ?? ''));
      } catch (err) {
        if (!cancelled) setError(errorMessage(err, 'Could not load projects.'));
      } finally {
        if (!cancelled) setLoading(false);
      }
    })();
    return () => { cancelled = true; };
  }, []);

  useEffect(() => {
    if (!projectId) { setGroups([]); setGroupId(''); return; }
    let cancelled = false;
    (async () => {
      setError('');
      try {
        const list = await projectsApi.listGroups(projectId);
        if (cancelled) return;
        setGroups(list || []);
        setGroupId((prev) => (list || []).some((g) => g.id === prev) ? prev : (list?.[0]?.id ?? ''));
      } catch (err) {
        if (!cancelled) setError(errorMessage(err, 'Could not load groups.'));
      }
    })();
    return () => { cancelled = true; };
  }, [projectId]);

  const loadReport = useCallback(async () => {
    if (!projectId || !groupId) { setReport(null); return; }
    setError('');
    try {
      setReport(await projectsApi.groupReport(projectId, groupId));
    } catch (err) {
      setReport(null);
      setError(errorMessage(err, 'Could not load the group report.'));
    }
  }, [projectId, groupId]);

  useEffect(() => { loadReport(); }, [loadReport]);

  const members = useMemo(() => {
    const rows = (report?.members || []).map((m) => {
      const rate = m.tasks_assigned > 0
        ? Math.round((m.tasks_completed / m.tasks_assigned) * 100)
        : 0;
      return {
        id: m.student_id,
        name: m.student_name || m.email,
        email: m.email,
        role: m.role,
        tasksAssigned: m.tasks_assigned,
        tasksCompleted: m.tasks_completed,
        contributions: m.contributions,
        rate,
        status: rate >= 70 ? 'On Track' : rate >= 50 ? 'Needs Attention' : 'At Risk',
      };
    });
    const term = searchTerm.trim().toLowerCase();
    return term
      ? rows.filter((m) => m.name.toLowerCase().includes(term) || m.email.toLowerCase().includes(term))
      : rows;
  }, [report, searchTerm]);

  const summary = report?.summary;

  return (
    <div className="space-y-6">
      <div>
        <h2 className="text-2xl font-bold text-text-primary">Individual Contribution Tracking</h2>
        <p className="text-text-secondary" style={{ fontSize: '14px' }}>
          Task completion and logged contributions per member, straight from the group report.
        </p>
      </div>

      {error ? (
        <div className="bg-red-50 border border-red-200 text-red-700 px-4 py-3 rounded-xl text-[13px] flex items-center gap-2">
          <AlertCircle size={16} /> {error}
        </div>
      ) : null}

      <div className="fet-card p-4 md:p-5">
        <div className="grid sm:grid-cols-2 gap-3">
          <div>
            <label className="fet-label">Project</label>
            <select
              className="fet-select"
              value={projectId}
              onChange={(e) => setProjectId(e.target.value)}
              disabled={loading || projects.length === 0}
            >
              {projects.length === 0 ? <option value="">No projects available</option> : null}
              {projects.map((p) => (
                <option key={p.id} value={p.id}>{p.title}</option>
              ))}
            </select>
          </div>
          <div>
            <label className="fet-label">Group</label>
            <select
              className="fet-select"
              value={groupId}
              onChange={(e) => setGroupId(e.target.value)}
              disabled={groups.length === 0}
            >
              {groups.length === 0 ? <option value="">No groups in this project</option> : null}
              {groups.map((g) => (
                <option key={g.id} value={g.id}>{g.name}</option>
              ))}
            </select>
          </div>
        </div>

        {summary ? (
          <div className="grid grid-cols-2 sm:grid-cols-5 gap-3 mt-4 pt-4 border-t border-border-default">
            {[
              { label: 'Members', value: summary.member_count },
              { label: 'Tasks', value: summary.total_tasks },
              { label: 'Completed', value: summary.completed_tasks },
              { label: 'In progress', value: summary.in_progress_tasks },
              { label: 'Contributions', value: summary.contribution_count },
            ].map((s) => (
              <div key={s.label}>
                <p className="text-[11px] text-text-secondary uppercase tracking-wider">{s.label}</p>
                <p className="text-[18px] font-bold text-text-primary">{s.value}</p>
              </div>
            ))}
          </div>
        ) : null}
      </div>

      <div className="flex flex-col sm:flex-row gap-4">
        <div className="relative flex-1">
          <Search className="absolute left-3 top-1/2 transform -translate-y-1/2 text-text-secondary" size={18} />
          <input
            type="text"
            placeholder="Search members..."
            value={searchTerm}
            onChange={(e) => setSearchTerm(e.target.value)}
            className="w-full pl-10 pr-4 py-2 fet-input"
          />
        </div>
        {report ? (
          <div className="flex items-center gap-2 text-[13px] text-text-secondary">
            <TrendingUp size={16} className="text-primary" />
            Group completion {summary.completion_rate}%
          </div>
        ) : null}
      </div>

      {!report ? (
        <div className="fet-card p-8 text-center">
          <FolderKanban size={32} className="mx-auto text-text-secondary/30" />
          <p className="text-[13px] text-text-secondary mt-2">
            {groups.length === 0
              ? 'This project has no groups yet.'
              : 'Choose a project and a group to see contributions.'}
          </p>
        </div>
      ) : members.length === 0 ? (
        <div className="fet-card p-8 text-center">
          <Users size={32} className="mx-auto text-text-secondary/30" />
          <p className="text-[13px] text-text-secondary mt-2">
            {searchTerm ? 'No member matches your search.' : 'This group has no members yet.'}
          </p>
        </div>
      ) : (
        <div className="grid grid-cols-1 gap-4">
          {members.map((m) => (
            <div key={m.id} className="fet-card p-5">
              <div className="flex flex-col md:flex-row md:items-start md:justify-between gap-4">
                <div className="flex items-start gap-4">
                  <div className="w-11 h-11 rounded-full bg-primary text-white flex items-center justify-center font-bold text-[15px] flex-shrink-0">
                    {(m.name || '?').split(' ').map((n) => n[0]).join('').slice(0, 2).toUpperCase()}
                  </div>
                  <div>
                    <div className="flex items-center gap-3 flex-wrap">
                      <h3 className="text-[15px] font-semibold text-text-primary">{m.name}</h3>
                      <span className={`${
                        m.status === 'On Track' ? 'fet-badge fet-badge-active'
                          : m.status === 'Needs Attention' ? 'fet-badge fet-badge-pending'
                            : 'fet-badge fet-badge-danger'
                      }`}>
                        {m.status}
                      </span>
                      {m.role === 'GROUP_LEADER' ? (
                        <span className="fet-badge fet-badge-info">Group Leader</span>
                      ) : null}
                    </div>
                    <p className="text-[12.5px] text-text-secondary">{m.email}</p>
                    <div className="flex flex-wrap gap-4 mt-2">
                      <div>
                        <p className="text-[11px] text-text-secondary">Tasks Completed</p>
                        <p className="text-[13px] font-semibold text-text-primary">
                          {m.tasksCompleted}/{m.tasksAssigned}
                        </p>
                      </div>
                      <div>
                        <p className="text-[11px] text-text-secondary">Contributions</p>
                        <p className="text-[13px] font-semibold text-text-primary">{m.contributions}</p>
                      </div>
                    </div>
                  </div>
                </div>

                <div className="bg-page-bg rounded-lg px-4 py-2 text-center min-w-[120px]">
                  <p className="text-[11px] text-text-secondary">Task Completion</p>
                  <p className="text-[22px] font-bold text-text-primary">{m.rate}%</p>
                  <div className="fet-progress-bar mt-1.5">
                    <div className="fet-progress-bar-fill" style={{ width: `${m.rate}%` }}></div>
                  </div>
                </div>
              </div>
            </div>
          ))}
        </div>
      )}

      {report?.recent_contributions?.length ? (
        <div className="fet-card p-5">
          <h3 className="text-[15px] font-semibold text-text-primary mb-4">Recent Contributions</h3>
          <div className="space-y-2">
            {report.recent_contributions.map((c) => (
              <div key={c.id} className="p-3 rounded-xl bg-page-bg">
                <p className="text-[13px] text-text-primary">{c.description}</p>
                <p className="text-[11px] text-text-secondary mt-0.5">
                  {c.student_name} · {formatDate(c.created_at)}
                </p>
              </div>
            ))}
          </div>
        </div>
      ) : null}
    </div>
  );
};

export default ContributionTracking;
