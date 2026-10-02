import React, { useState, useEffect } from 'react';
import { Users, FolderKanban, Building, Briefcase, UserPlus, PlusCircle, ArrowRight } from 'lucide-react';
import { useNavigate } from 'react-router-dom';
import StatsCard from './StatsCard';
import ActivityFeed from './ActivityFeed';
import { useAppContext } from '../../context/AppContext';

const CoordinatorDashboard = ({ user }) => {
  const navigate = useNavigate();
  const { students, lecturers, projects, tasks } = useAppContext();
  const [stats, setStats] = useState({ students: 0, lecturers: 0, projects: 0, tasks: 0 });
  const [departmentName, setDepartmentName] = useState(user?.department || 'Computer Engineering');

  useEffect(() => {
    const dept = user?.department || 'Computer Engineering';
    setStats({
      students: students.filter(s => s.department === dept).length,
      lecturers: lecturers.filter(l => l.department === dept).length,
      projects: projects.filter(p => p.department === dept).length,
      tasks: tasks.length,
    });
  }, [students, lecturers, projects, tasks, user]);

  const statCards = [
    { icon: Users, label: 'Students', value: stats.students, color: 'secondary' },
    { icon: Briefcase, label: 'Lecturers', value: stats.lecturers, color: 'tertiary' },
    { icon: FolderKanban, label: 'Projects', value: stats.projects, color: 'success' },
    { icon: Building, label: 'Department', value: user?.department || 'CS', color: 'info' },
  ];

  const quickActions = [
    { label: 'Add Student', icon: UserPlus, action: () => navigate('/admin/users') },
    { label: 'Add Lecturer', icon: UserPlus, action: () => navigate('/admin/users') },
    { label: 'New Project', icon: FolderKanban, action: () => navigate('/projects') },
    { label: 'Assessment', icon: PlusCircle, action: () => navigate('/assessment') },
  ];

  return (
    <div className="space-y-5 max-w-7xl mx-auto">
      <div className="fet-welcome-banner">
        <div className="relative z-10">
          <h2 className="text-[20px] md:text-[22px] font-bold">Welcome, {user?.fullName || 'Coordinator'}</h2>
          <p className="text-white/50 text-[13px] mt-0.5">{departmentName} Department</p>
        </div>
      </div>

      <div className="grid grid-cols-2 lg:grid-cols-4 gap-3 md:gap-4">
        {statCards.map((stat, i) => (
          <StatsCard key={i} {...stat} />
        ))}
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-4 md:gap-5">
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

        <ActivityFeed />
      </div>
    </div>
  );
};

export default CoordinatorDashboard;
