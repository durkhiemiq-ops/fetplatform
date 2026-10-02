import React, { useState, useEffect, useCallback } from 'react';
import {
  Users, FolderKanban, Building, Briefcase, UserPlus, PlusCircle,
  ArrowRight, AlertCircle,
} from 'lucide-react';
import { useNavigate } from 'react-router-dom';
import StatsCard from './StatsCard';
import ActivityFeed from './ActivityFeed';
import { dashboardApi } from '../../lib/dashboard';
import { projectsApi } from '../../lib/projects';
import { notificationsApi } from '../../lib/notifications';
import { errorMessage } from '../../lib/enrollment';
import { relativeTime } from '../../lib/format';

const CoordinatorDashboard = ({ user }) => {
  const navigate = useNavigate();
  const [stats, setStats] = useState({ students: 0, lecturers: 0, projects: 0 });
  const [projects, setProjects] = useState([]);
  const [activity, setActivity] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');

  // The department comes from the signed-in user's own profile, not a constant.
  const departmentName = user?.lecturer_profile?.department?.name
    || user?.student_profile?.department?.name
    || 'Engineering';

  const load = useCallback(async () => {
    setError('');
    try {
      const [dash, list, notes] = await Promise.all([
        dashboardApi.get(),
        projectsApi.listProjects().catch(() => []),
        notificationsApi.list().catch(() => []),
      ]);
      setStats({
        students: dash?.stats?.total_students ?? dash?.total_students ?? 0,
        lecturers: dash?.stats?.total_lecturers ?? dash?.total_lecturers ?? 0,
        projects: (list || []).length,
      });
      setProjects(list || []);
      setActivity(notes || []);
    } catch (err) {
      setError(errorMessage(err, 'Could not load the dashboard.'));
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { load(); }, [load]);

  const statCards = [
    { icon: Users, label: 'Students', value: stats.students, color: 'secondary' },
    { icon: Briefcase, label: 'Lecturers', value: stats.lecturers, color: 'tertiary' },
    { icon: FolderKanban, label: 'Projects', value: stats.projects, color: 'success' },
    { icon: Building, label: 'Department', value: user?.lecturer_profile?.department?.code || '—', color: 'info' },
  ];

  // Adding people now happens through roster upload, which is what actually
  // creates accounts server-side.
  const quickActions = [
    { label: 'Add Student', icon: UserPlus, action: () => navigate('/admin/roster') },
    { label: 'Add Lecturer', icon: UserPlus, action: () => navigate('/admin/roster') },
    { label: 'New Project', icon: FolderKanban, action: () => navigate('/projects') },
    { label: 'Assessment', icon: PlusCircle, action: () => navigate('/assessment') },
  ];

  const active = projects
    .filter((p) => p.status === 'ACTIVE')
    .slice(0, 5);
  const pct = (p) => (p.task_count > 0
    ? Math.round((p.completed_task_count / p.task_count) * 100)
    : 0);

  return (
    <div className="space-y-5 max-w-7xl mx-auto">
      <div className="fet-welcome-banner">
        <div className="relative z-10">
          <h2 className="text-[20px] md:text-[22px] font-bold">Welcome, {user?.fullName || 'Coordinator'}</h2>
          <p className="text-white/50 text-[13px] mt-0.5">{departmentName} Department</p>
        </div>
      </div>

      {error ? (
        <div className="bg-red-50 border border-red-200 text-red-700 px-4 py-3 rounded-xl text-[13px] flex items-center gap-2">
          <AlertCircle size={16} /> {error}
          <button onClick={load} className="ml-auto underline">Retry</button>
        </div>
      ) : null}

      <div className="grid grid-cols-2 lg:grid-cols-4 gap-3 md:gap-4">
        {statCards.map((stat, i) => (
          <StatsCard key={i} {...stat} />
        ))}
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-4 md:gap-5">
        <div className="space-y-4 md:space-y-5">
          <div className="fet-card p-5">
            <h3 className="text-[15px] font-semibold text-text-primary mb-4">Quick Actions</h3>
            <div className="grid grid-cols-2 gap-3">
              {quickActions.map((action) => {
                const Icon = action.icon;
                return (
                  <button
                    key={action.label}
                    onClick={action.action}
                    className="flex items-center gap-2.5 p-3.5 rounded-xl bg-page-bg hover:bg-primary-light text-[13px] font-medium text-text-primary transition-colors"
                  >
                    <Icon size={16} className="text-primary" strokeWidth={2} /> {action.label}
                  </button>
                );
              })}
            </div>
            <button
              onClick={() => navigate('/projects')}
              className="fet-btn-primary mt-4 w-full py-2.5"
            >
              View All Projects <ArrowRight size={15} />
            </button>
          </div>

          <div className="fet-card p-5">
            <h3 className="text-[15px] font-semibold text-text-primary mb-4">Active Projects</h3>
            {loading ? (
              <p className="text-center text-text-secondary py-6 text-[13px]">Loading projects...</p>
            ) : active.length === 0 ? (
              <p className="text-center text-text-secondary py-6 text-[13px]">No active projects</p>
            ) : (
              <div className="space-y-3">
                {active.map((p) => (
                  <button
                    key={p.id}
                    onClick={() => navigate(`/projects/${p.id}`)}
                    className="block w-full text-left p-3 rounded-xl bg-page-bg hover:bg-primary-light transition-colors"
                  >
                    <div className="flex items-start justify-between gap-2">
                      <div className="min-w-0">
                        <p className="font-medium text-text-primary text-[13px] truncate">{p.title}</p>
                        <p className="text-[11.5px] text-text-secondary">
                          {p.course_code} · {p.completed_task_count}/{p.task_count} tasks
                        </p>
                      </div>
                      <span className="text-[12px] font-semibold text-text-primary shrink-0">{pct(p)}%</span>
                    </div>
                    <div className="fet-progress-bar mt-2">
                      <div className="fet-progress-bar-fill" style={{ width: `${pct(p)}%` }}></div>
                    </div>
                  </button>
                ))}
              </div>
            )}
          </div>
        </div>

        <ActivityFeed
          activities={activity.slice(0, 5).map((n) => ({
            id: n.id,
            user: 'FET',
            system: true,
            action: `${n.title}${n.message ? ` — ${n.message}` : ''}`,
            time: relativeTime(n.created_at),
          }))}
        />
      </div>
    </div>
  );
};

export default CoordinatorDashboard;
