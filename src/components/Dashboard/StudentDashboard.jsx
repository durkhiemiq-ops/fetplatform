import React, { useState, useEffect, useMemo } from 'react';
import { useAppContext } from '../../context/AppContext';
import {
  BookOpen, Clock, CheckCircle, Bell,
  FolderKanban, ListTodo, AlertCircle
} from 'lucide-react';
import StatsCard from './StatsCard';
import ActivityFeed from './ActivityFeed';
import { taskStatusLabel } from '../../utils/mappers';

/**
 * StudentDashboard — reads only real API data.
 *
 * H5/M4: previously this imported the (now-emptied) mockData stub and read
 * `t.assignedTo` (a matricule), `project.progress` and `project.deadline` —
 * none of which exist on the backend. Tasks key on `assignee` (a user UUID);
 * Project has no progress/deadline columns; ProjectTask has no due_date.
 * Membership (not a group-name lookup) is the authoritative project link.
 */
const StudentDashboard = ({ user }) => {
  const {
    activities,
    currentSemester,
    currentSchoolYear,
    tasks: allTasks,
    announcements: allAnnouncements,
    projects: allProjects,
    memberships,
    enrollments,
    getCurrentSemesterStats,
  } = useAppContext();

  const [stats, setStats] = useState({
    totalCourses: 0,
    attendance: 0,
    pendingTasks: 0,
    completedTasks: 0,
    activeProjects: 0,
  });
  const [recentAnnouncements, setRecentAnnouncements] = useState([]);

  const myUserId = user?.id;

  // H5: `assignee` is a user UUID, so the filter must compare against the
  // authenticated user's id — comparing to a matricule could never match.
  const myTasks = useMemo(
    () => allTasks.filter((t) => t.assignee && t.assignee === myUserId),
    [allTasks, myUserId]
  );

  // Membership rows are the authoritative "which projects am I in" link.
  const myProjectIds = useMemo(
    () => new Set(memberships.filter((m) => m.studentId === myUserId).map((m) => m.projectId)),
    [memberships, myUserId]
  );
  const studentProjects = useMemo(
    () => allProjects.filter((p) => myProjectIds.has(p.id)),
    [allProjects, myProjectIds]
  );

  useEffect(() => {
    const pendingTasks = myTasks.filter((t) => t.status !== 'completed');
    const completedTasks = myTasks.filter((t) => t.status === 'completed');
    const semStats = getCurrentSemesterStats();

    setStats({
      totalCourses: (enrollments || []).length,
      attendance: semStats?.attendance || 0,
      pendingTasks: pendingTasks.length,
      completedTasks: completedTasks.length,
      activeProjects: studentProjects.length,
    });

    setRecentAnnouncements(allAnnouncements.slice(0, 3));
  }, [enrollments, myTasks, studentProjects, allAnnouncements, getCurrentSemesterStats]);

  const studentName = user?.fullName || 'Student';

  const statCards = [
    { icon: FolderKanban, label: 'My Projects', value: stats.activeProjects, color: 'secondary' },
    { icon: ListTodo, label: 'Pending Tasks', value: stats.pendingTasks, color: 'warning' },
    { icon: CheckCircle, label: 'Completed Tasks', value: stats.completedTasks, color: 'success' },
    { icon: BookOpen, label: 'Enrolled Courses', value: stats.totalCourses, color: 'info' },
  ];

  const getTaskStatusBadge = (status) => {
    switch (status) {
      case 'completed': return 'fet-badge fet-badge-completed';
      case 'in_progress': return 'fet-badge fet-badge-warning';
      default: return 'fet-badge fet-badge-inactive';
    }
  };

  const getTaskStatusIcon = (status) => {
    switch (status) {
      case 'completed': return <CheckCircle size={14} className="text-success" />;
      case 'in_progress': return <Clock size={14} className="text-warning" />;
      default: return <AlertCircle size={14} className="text-text-secondary" />;
    }
  };

  const recentActivities = (activities || []).slice(0, 5).map((a) => ({
    user: a.user,
    action: a.action,
    time:
      new Date(a.time).toLocaleDateString() +
      ' ' +
      new Date(a.time).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }),
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
            <p className="text-white/50 text-[13px] mt-1">Here's what's happening with your projects today.</p>
            <p className="text-white/35 text-[12px] mt-0.5">
              {currentSemester?.name} {currentSchoolYear?.name}
            </p>
          </div>
          <div className="bg-white/10 backdrop-blur-sm rounded-xl px-5 py-3 text-center min-w-[100px] border border-white/10">
            <p className="text-[11px] text-white/50 font-medium uppercase tracking-wider">Attendance</p>
            <p className="text-[26px] font-bold text-white leading-tight">{stats.attendance}%</p>
          </div>
        </div>
      </div>

      <div className="grid grid-cols-2 lg:grid-cols-4 gap-3 md:gap-4">
        {statCards.map((stat, index) => (
          <StatsCard key={index} {...stat} />
        ))}
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-4 md:gap-5">
        <div className="lg:col-span-2 space-y-4 md:space-y-5">
          {/* My Projects — no progress bar: Project has no progress column. */}
          <div className="fet-card p-4 md:p-5">
            <div className="flex items-center justify-between mb-4">
              <h3 className="text-[14px] md:text-[15px] font-semibold text-text-primary flex items-center gap-2">
                <FolderKanban size={16} className="text-primary" strokeWidth={2} />
                My Projects
              </h3>
            </div>
            <div className="space-y-3">
              {studentProjects.length > 0 ? (
                studentProjects.slice(0, 3).map((project) => (
                  <div
                    key={project.id}
                    className="p-3.5 rounded-xl border border-border-default hover:shadow-card transition-shadow"
                  >
                    <div className="flex flex-col sm:flex-row items-start sm:justify-between gap-2">
                      <div>
                        <h4 className="font-semibold text-text-primary text-[13.5px]">{project.title}</h4>
                        <p className="text-[12px] text-text-secondary mt-0.5">
                          {project.supervisorName
                            ? `Supervisor: ${project.supervisorName}`
                            : 'No supervisor assigned'}
                        </p>
                      </div>
                      <span
                        className={`fet-badge ${
                          project.status === 'active' ? 'fet-badge-active' : 'fet-badge-pending'
                        } self-start`}
                      >
                        {project.status}
                      </span>
                    </div>
                  </div>
                ))
              ) : (
                <div className="text-center py-8">
                  <FolderKanban size={32} className="mx-auto text-text-secondary/30" />
                  <p className="text-[13px] text-text-secondary mt-2">No projects assigned</p>
                </div>
              )}
            </div>
          </div>

          {/* My Tasks — no due date column exists on ProjectTask. */}
          <div className="fet-card p-4 md:p-5">
            <div className="flex items-center justify-between mb-4">
              <h3 className="text-[14px] md:text-[15px] font-semibold text-text-primary flex items-center gap-2">
                <ListTodo size={16} className="text-primary" strokeWidth={2} />
                My Tasks
              </h3>
            </div>
            <div className="space-y-2">
              {myTasks.length > 0 ? (
                myTasks.slice(0, 4).map((task) => {
                  const project = allProjects.find((p) => p.id === task.project);
                  return (
                    <div key={task.id} className="flex items-center justify-between p-3 rounded-xl bg-page-bg gap-3">
                      <div className="flex items-center gap-3 flex-1 min-w-0">
                        <div
                          className="w-8 h-8 rounded-lg flex items-center justify-center flex-shrink-0"
                          style={{ backgroundColor: 'rgba(63,53,181,0.08)' }}
                        >
                          {getTaskStatusIcon(task.status)}
                        </div>
                        <div className="flex-1 min-w-0">
                          <p className="font-medium text-text-primary text-[13px] truncate">{task.title}</p>
                          <p className="text-[11px] text-text-secondary truncate">{project?.title || 'Project'}</p>
                        </div>
                      </div>
                      <span className={getTaskStatusBadge(task.status)}>{taskStatusLabel(task.status)}</span>
                    </div>
                  );
                })
              ) : (
                <div className="text-center py-8">
                  <ListTodo size={32} className="mx-auto text-text-secondary/30" />
                  <p className="text-[13px] text-text-secondary mt-2">No tasks assigned to you</p>
                </div>
              )}
            </div>
          </div>
        </div>

        <div className="space-y-4 md:space-y-5">
          <div className="fet-card p-4 md:p-5">
            <h3 className="text-[14px] md:text-[15px] font-semibold text-text-primary flex items-center gap-2 mb-4">
              <Bell size={16} className="text-primary" strokeWidth={2} />
              Announcements
            </h3>
            <div className="space-y-2">
              {recentAnnouncements.length === 0 ? (
                <p className="text-center text-text-secondary py-4 text-[13px]">No announcements</p>
              ) : (
                recentAnnouncements.map((a) => (
                  <div key={a.id} className="p-3 rounded-xl bg-page-bg">
                    <p className="font-medium text-text-primary text-[13px]">{a.title}</p>
                    <p className="text-[11px] text-text-secondary mt-0.5 line-clamp-2">{a.content}</p>
                    {a.date && (
                      <p className="text-[10px] text-text-secondary mt-1 font-medium">
                        {new Date(a.date).toLocaleDateString()}
                      </p>
                    )}
                  </div>
                ))
              )}
            </div>
          </div>

          <ActivityFeed activities={recentActivities} />
        </div>
      </div>
    </div>
  );
};

export default StudentDashboard;
