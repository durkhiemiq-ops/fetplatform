import React, { useState, useEffect } from 'react';
import { Users, BookOpen, FolderKanban, Building, UserPlus, AlertCircle, Shield } from 'lucide-react';
import { useNavigate } from 'react-router-dom';
import { useAppContext } from '../../context/AppContext';
import StatsCard from '../../components/Dashboard/StatsCard';

const AdminDashboard = ({ user }) => {
  const navigate = useNavigate();
  const { students, lecturers, courses, projects } = useAppContext();
  const [stats, setStats] = useState({
    totalStudents: 0,
    totalLecturers: 0,
    totalCourses: 0,
    totalDepartments: 0,
    activeProjects: 0,
    pendingIssues: 0,
  });

  useEffect(() => {
    setStats({
      totalStudents: students.length,
      totalLecturers: lecturers.length,
      totalCourses: courses.length,
      totalDepartments: 5,
      activeProjects: projects.filter(p => p.status === 'Active').length,
      pendingIssues: 0,
    });
  }, [students, lecturers, courses, projects]);

  const statCards = [
    { icon: Users, label: 'Total Students', value: stats.totalStudents, color: 'secondary' },
    { icon: UserPlus, label: 'Total Lecturers', value: stats.totalLecturers, color: 'tertiary' },
    { icon: BookOpen, label: 'Total Courses', value: stats.totalCourses, color: 'success' },
    { icon: Building, label: 'Departments', value: stats.totalDepartments, color: 'info' },
    { icon: FolderKanban, label: 'Active Projects', value: stats.activeProjects, color: 'warning' },
    { icon: AlertCircle, label: 'Pending Issues', value: stats.pendingIssues, color: 'error' },
  ];

  return (
    <div className="space-y-5 max-w-7xl mx-auto">
      <div className="fet-welcome-banner">
        <div className="relative z-10 flex items-center gap-3">
          <div className="w-11 h-11 rounded-xl flex items-center justify-center bg-white/10 border border-white/10">
            <Shield size={22} className="text-white" />
          </div>
          <div>
            <h2 className="text-[20px] md:text-[22px] font-bold">Admin Dashboard</h2>
            <p className="text-white/50 text-[13px]">Faculty of Engineering and Technology</p>
          </div>
        </div>
      </div>

      <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-3 gap-3 md:gap-4">
        {statCards.map((stat, index) => (
          <StatsCard key={index} {...stat} />
        ))}
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-4 md:gap-5">
        <div className="fet-card p-5">
          <h3 className="text-[15px] font-semibold text-text-primary mb-4">Quick Actions</h3>
          <div className="grid grid-cols-2 gap-3">
            <button onClick={() => navigate('/admin/users')} className="flex items-center gap-2.5 p-3.5 rounded-xl bg-page-bg hover:bg-primary-light text-[13px] font-medium text-text-primary transition-colors">
              <Users size={16} className="text-primary" /> Manage Users
            </button>
            <button onClick={() => navigate('/courses')} className="flex items-center gap-2.5 p-3.5 rounded-xl bg-page-bg hover:bg-primary-light text-[13px] font-medium text-text-primary transition-colors">
              <BookOpen size={16} className="text-primary" /> Course Catalogue
            </button>
            <button onClick={() => navigate('/projects')} className="flex items-center gap-2.5 p-3.5 rounded-xl bg-page-bg hover:bg-primary-light text-[13px] font-medium text-text-primary transition-colors">
              <FolderKanban size={16} className="text-primary" /> Projects
            </button>
            <button onClick={() => navigate('/academic')} className="flex items-center gap-2.5 p-3.5 rounded-xl bg-page-bg hover:bg-primary-light text-[13px] font-medium text-text-primary transition-colors">
              <Building size={16} className="text-primary" /> Academic Setup
            </button>
          </div>
        </div>

        <div className="fet-card p-5">
          <h3 className="text-[15px] font-semibold text-text-primary mb-4">Recent Activity</h3>
          <div className="space-y-2">
            <div className="flex items-center gap-3 p-3 rounded-xl bg-page-bg">
              <div className="w-8 h-8 rounded-lg flex items-center justify-center" style={{ backgroundColor: 'rgba(22,163,74,0.1)' }}>
                <UserPlus size={14} className="text-success" />
              </div>
              <div>
                <p className="text-[13px] font-medium text-text-primary">New student enrolled</p>
                <p className="text-[11px] text-text-secondary">2 mins ago</p>
              </div>
            </div>
            <div className="flex items-center gap-3 p-3 rounded-xl bg-page-bg">
              <div className="w-8 h-8 rounded-lg flex items-center justify-center" style={{ backgroundColor: 'rgba(63,53,181,0.1)' }}>
                <BookOpen size={14} className="text-primary" />
              </div>
              <div>
                <p className="text-[13px] font-medium text-text-primary">Course added: CEF444</p>
                <p className="text-[11px] text-text-secondary">1 hour ago</p>
              </div>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
};

export default AdminDashboard;
