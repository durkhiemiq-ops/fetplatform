import React, { useState, useEffect, useCallback } from 'react';
import { useNavigate } from 'react-router-dom';
import {
  BookOpen, Clock, CheckCircle, Calendar,
  FolderKanban, ListTodo, AlertCircle, Bell,
} from 'lucide-react';
import StatsCard from './StatsCard';
import ActivityFeed from './ActivityFeed';
import { dashboardApi } from '../../lib/dashboard';
import { notificationsApi } from '../../lib/notifications';
import { learningApi } from '../../lib/learning';
import { errorMessage } from '../../lib/enrollment';
import { formatDate, formatClock, relativeTime } from '../../lib/format';

const EMPTY = {
  stats: { enrolled_courses: 0, attendance_rate: '0%', active_projects: 0, pending_tasks: 0 },
  courses: [],
  today_classes: [],
  announcements: [],
  active_projects: [],
  pending_tasks: [],
  attendance: { total_sessions: 0, attended: 0, rate: 0 },
};

const statusBadge = (status) => {
  const cls = {
    COMPLETED: 'fet-badge fet-badge-completed',
    IN_PROGRESS: 'fet-badge fet-badge-warning',
    ACTIVE: 'fet-badge fet-badge-active',
    DRAFT: 'fet-badge fet-badge-pending',
  }[status] || 'fet-badge fet-badge-inactive';
  return <span className={cls}>{String(status || '').replace(/_/g, ' ')}</span>;
};

const priorityBadge = (priority) => {
  const cls = { HIGH: 'fet-badge-danger', MEDIUM: 'fet-badge-warning', LOW: 'fet-badge-info' }[priority]
    || 'fet-badge-info';
  return <span className={cls}>{priority}</span>;
};

const StudentDashboard = ({ user }) => {
  const navigate = useNavigate();
  const [data, setData] = useState(EMPTY);
  const [myCourses, setMyCourses] = useState([]);
  const [activity, setActivity] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');

  const load = useCallback(async () => {
    setError('');
    try {
      // One aggregate call rather than fanning out to five endpoints, then the
      // two things it does not cover: the student's own course list, and the
      // notification stream the backend raises on its own.
      const [dash, courses, notes] = await Promise.all([
        dashboardApi.get(),
        learningApi.getMyCourses('student'),
        notificationsApi.list().catch(() => []),
      ]);
      setData({ ...EMPTY, ...(dash || {}) });
      setMyCourses(courses || []);
      setActivity(notes || []);
    } catch (err) {
      setError(errorMessage(err, 'Could not load your dashboard.'));
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { load(); }, [load]);

  const studentName = user?.fullName || 'Student';
  const rate = Number(String(data.stats.attendance_rate || '0').replace('%', '')) || 0;

  const statCards = [
    { icon: FolderKanban, label: 'Active Projects', value: data.stats.active_projects, color: 'secondary' },
    { icon: ListTodo, label: 'Pending Tasks', value: data.stats.pending_tasks, color: 'warning' },
    { icon: BookOpen, label: 'Enrolled Courses', value: data.stats.enrolled_courses, color: 'info' },
    { icon: CheckCircle, label: 'Attendance', value: `${rate}%`, color: 'success' },
  ];

  // Notifications are the platform's own record of what happened to you.
  const recentActivities = activity.slice(0, 5).map((n) => ({
    id: n.id,
    user: 'FET',
    system: true,
    action: `${n.title}${n.message ? ` — ${n.message}` : ''}`,
    time: relativeTime(n.created_at),
  }));

  if (!user) {
    return (
      <div className="min-h-screen flex items-center justify-center">
        <div className="w-8 h-8 border-[3px] border-primary border-t-transparent rounded-full animate-spin"></div>
      </div>
    );
  }

  return (
    <div className="space-y-5 max-w-7xl mx-auto">
      <div className="fet-welcome-banner">
        <div className="relative z-10 flex flex-col sm:flex-row items-start sm:items-center justify-between gap-4">
          <div>
            <h2 className="text-[20px] md:text-[22px] font-bold">Welcome back, {studentName}</h2>
            <p className="text-white/50 text-[13px] mt-1">Here&apos;s what&apos;s happening today.</p>
            <p className="text-white/35 text-[12px] mt-0.5">
              {myCourses.length > 0
                ? `${myCourses.length} course${myCourses.length === 1 ? '' : 's'} this semester`
                : 'Not enrolled in any courses yet'}
            </p>
          </div>
          <div className="bg-white/10 backdrop-blur-sm rounded-xl px-5 py-3 text-center min-w-[100px] border border-white/10">
            <p className="text-[11px] text-white/50 font-medium uppercase tracking-wider">Attendance</p>
            <p className="text-[26px] font-bold text-white leading-tight">{rate}%</p>
          </div>
        </div>
      </div>

      {error ? (
        <div className="bg-red-50 border border-red-200 text-red-700 px-4 py-3 rounded-xl text-[13px] flex items-center gap-2">
          <AlertCircle size={16} /> {error}
          <button onClick={load} className="ml-auto underline">Retry</button>
        </div>
      ) : null}

      <div className="grid grid-cols-2 lg:grid-cols-4 gap-3 md:gap-4">
        {statCards.map((stat, index) => (
          <StatsCard key={index} {...stat} />
        ))}
      </div>

      {data.today_classes?.length > 0 ? (
        <div className="fet-card p-4 md:p-5">
          <h3 className="text-[14px] md:text-[15px] font-semibold text-text-primary flex items-center gap-2 mb-4">
            <Calendar size={16} className="text-primary" strokeWidth={2} />
            Today&apos;s Classes
          </h3>
          <div className="grid sm:grid-cols-2 lg:grid-cols-3 gap-2">
            {data.today_classes.map((c) => (
              <button
                key={c.session_id}
                onClick={() => navigate('/attendance')}
                className="p-3 rounded-xl bg-page-bg text-left hover:bg-primary-light transition-colors"
              >
                <p className="font-medium text-text-primary text-[13px]">{c.class_name}</p>
                <p className="text-[11.5px] text-text-secondary mt-0.5">
                  {c.course_code} · {formatClock(new Date(c.starts_at).toTimeString().slice(0, 5))}
                  {c.location ? ` · ${c.location}` : ''}
                </p>
              </button>
            ))}
          </div>
        </div>
      ) : null}

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-4 md:gap-5">
        <div className="lg:col-span-2 space-y-4 md:space-y-5">
          {/* My Projects */}
          <div className="fet-card p-4 md:p-5">
            <div className="flex items-center justify-between mb-4">
              <h3 className="text-[14px] md:text-[15px] font-semibold text-text-primary flex items-center gap-2">
                <FolderKanban size={16} className="text-primary" strokeWidth={2} />
                My Projects
              </h3>
              <button onClick={() => navigate('/projects')} className="text-[12px] text-primary hover:underline">
                View all
              </button>
            </div>
            <div className="space-y-3">
              {loading ? (
                <p className="text-center text-text-secondary py-8 text-[13px]">Loading projects...</p>
              ) : data.active_projects.length > 0 ? (
                data.active_projects.slice(0, 3).map((p) => {
                  const pct = p.task_count > 0
                    ? Math.round((p.completed_task_count / p.task_count) * 100)
                    : 0;
                  return (
                    <button
                      key={p.id}
                      onClick={() => navigate(`/projects/${p.id}`)}
                      className="block w-full text-left p-3.5 rounded-xl border border-border-default hover:shadow-card transition-shadow"
                    >
                      <div className="flex flex-col sm:flex-row sm:items-start sm:justify-between gap-2">
                        <div className="min-w-0">
                          <h4 className="font-semibold text-text-primary text-[13.5px]">{p.title}</h4>
                          <p className="text-[12px] text-text-secondary mt-0.5">
                            {p.course_code}{p.group_name ? ` · ${p.group_name}` : ''}
                          </p>
                        </div>
                        {statusBadge(p.status)}
                      </div>
                      <div className="mt-3">
                        <div className="flex items-center justify-between text-[12px] text-text-secondary mb-1.5">
                          <span>{p.completed_task_count}/{p.task_count} tasks</span>
                          <span className="font-semibold text-text-primary">{pct}%</span>
                        </div>
                        <div className="fet-progress-bar">
                          <div className="fet-progress-bar-fill" style={{ width: `${pct}%` }}></div>
                        </div>
                        {p.deadline ? (
                          <p className="text-[11px] text-text-secondary mt-1.5">
                            Deadline: {formatDate(p.deadline)}
                          </p>
                        ) : null}
                      </div>
                    </button>
                  );
                })
              ) : (
                <div className="text-center py-8">
                  <FolderKanban size={32} className="mx-auto text-text-secondary/30" />
                  <p className="text-[13px] text-text-secondary mt-2">No projects assigned</p>
                </div>
              )}
            </div>
          </div>

          {/* My Tasks */}
          <div className="fet-card p-4 md:p-5">
            <div className="flex items-center justify-between mb-4">
              <h3 className="text-[14px] md:text-[15px] font-semibold text-text-primary flex items-center gap-2">
                <ListTodo size={16} className="text-primary" strokeWidth={2} />
                My Tasks
              </h3>
              <button onClick={() => navigate('/projects')} className="text-[12px] text-primary hover:underline">
                View all
              </button>
            </div>
            <div className="space-y-2">
              {loading ? (
                <p className="text-center text-text-secondary py-6 text-[13px]">Loading tasks...</p>
              ) : data.pending_tasks.length > 0 ? (
                data.pending_tasks.slice(0, 4).map((t) => (
                  <div key={t.id} className="flex items-center justify-between p-3 rounded-xl bg-page-bg gap-3">
                    <div className="flex items-center gap-3 flex-1 min-w-0">
                      <div
                        className="w-8 h-8 rounded-lg flex items-center justify-center flex-shrink-0"
                        style={{ backgroundColor: 'rgba(63,53,181,0.08)' }}
                      >
                        {t.status === 'IN_PROGRESS'
                          ? <Clock size={14} className="text-warning" />
                          : <ListTodo size={14} className="text-text-secondary" />}
                      </div>
                      <div className="flex-1 min-w-0">
                        <p className="font-medium text-text-primary text-[13px] truncate">{t.title}</p>
                        <p className="text-[11px] text-text-secondary truncate">{t.project}</p>
                      </div>
                    </div>
                    {statusBadge(t.status)}
                  </div>
                ))
              ) : (
                <div className="text-center py-8">
                  <ListTodo size={32} className="mx-auto text-text-secondary/30" />
                  <p className="text-[13px] text-text-secondary mt-2">No tasks assigned</p>
                </div>
              )}
            </div>
          </div>
        </div>

        <div className="space-y-4 md:space-y-5">
          {/* Upcoming Deadlines */}
          <div className="fet-card p-4 md:p-5">
            <h3 className="text-[14px] md:text-[15px] font-semibold text-text-primary flex items-center gap-2 mb-4">
              <Clock size={16} className="text-warning" strokeWidth={2} />
              Upcoming Deadlines
            </h3>
            <div className="space-y-2">
              {data.pending_tasks.filter((t) => t.due_at).length > 0 ? (
                data.pending_tasks
                  .filter((t) => t.due_at)
                  .sort((a, b) => new Date(a.due_at) - new Date(b.due_at))
                  .slice(0, 4)
                  .map((t) => (
                    <div key={t.id} className="p-3 rounded-xl bg-page-bg">
                      <div className="flex items-start justify-between gap-2">
                        <div className="min-w-0">
                          <p className="font-medium text-text-primary text-[13px] truncate">{t.title}</p>
                          <p className="text-[11px] text-text-secondary mt-0.5">
                            {t.project} · Due {formatDate(t.due_at)}
                          </p>
                        </div>
                        <span className="self-start flex-shrink-0">{priorityBadge(t.priority)}</span>
                      </div>
                    </div>
                  ))
              ) : (
                <p className="text-center text-text-secondary py-4 text-[13px]">No upcoming deadlines</p>
              )}
            </div>
          </div>

          {/* Announcements */}
          <div className="fet-card p-4 md:p-5">
            <div className="flex items-center justify-between mb-4">
              <h3 className="text-[14px] md:text-[15px] font-semibold text-text-primary flex items-center gap-2">
                <Bell size={16} className="text-primary" strokeWidth={2} />
                Announcements
              </h3>
              <button onClick={() => navigate('/announcements')} className="text-[12px] text-primary hover:underline">
                View all
              </button>
            </div>
            <div className="space-y-2">
              {data.announcements.length > 0 ? (
                data.announcements.map((a) => (
                  <button
                    key={a.id}
                    onClick={() => navigate('/announcements')}
                    className="block w-full text-left p-3 rounded-xl bg-page-bg hover:bg-primary-light transition-colors"
                  >
                    <p className="font-medium text-text-primary text-[13px]">{a.title}</p>
                    <p className="text-[10px] text-text-secondary mt-1 font-medium">
                      {a.scope ? a.scope.replace(/_/g, ' ').toLowerCase() : ''} · {relativeTime(a.created_at)}
                    </p>
                  </button>
                ))
              ) : (
                <p className="text-center text-text-secondary py-4 text-[13px]">No announcements</p>
              )}
            </div>
          </div>

          {recentActivities.length > 0 ? <ActivityFeed activities={recentActivities} /> : null}
        </div>
      </div>
    </div>
  );
};

export default StudentDashboard;
