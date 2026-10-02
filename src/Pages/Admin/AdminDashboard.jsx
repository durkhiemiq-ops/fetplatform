import React, { useState, useEffect } from 'react';
import { Users, BookOpen, FolderKanban, Building, UserPlus, AlertCircle, GraduationCap, Layers, Upload, Building2, FilePlus2 } from 'lucide-react';
import { useNavigate } from 'react-router-dom';
import { academicsApi } from '../../lib/academics';
import { errorMessage } from '../../lib/enrollment';
import StatsCard from '../../components/Dashboard/StatsCard';

const EMPTY = {
  total_students: 0,
  total_lecturers: 0,
  total_courses: 0,
  total_departments: 0,
  total_offerings: 0,
  total_enrollments: 0,
  active_semester: null,
};

const AdminDashboard = ({ user }) => {
  const navigate = useNavigate();
  const [stats, setStats] = useState(EMPTY);
  const [loadError, setLoadError] = useState('');

  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        const data = await academicsApi.adminStats();
        if (!cancelled) setStats({ ...EMPTY, ...(data || {}) });
      } catch (err) {
        if (!cancelled) setLoadError(errorMessage(err, 'Could not load platform statistics.'));
      }
    })();
    return () => { cancelled = true; };
  }, []);

  const statCards = [
    { icon: Users, label: 'Total Students', value: stats.total_students, color: 'secondary' },
    { icon: UserPlus, label: 'Total Lecturers', value: stats.total_lecturers, color: 'tertiary' },
    { icon: BookOpen, label: 'Total Courses', value: stats.total_courses, color: 'success' },
    { icon: Building, label: 'Departments', value: stats.total_departments, color: 'info' },
    { icon: Layers, label: 'Offerings this semester', value: stats.total_offerings, color: 'warning' },
    { icon: GraduationCap, label: 'Enrolments this semester', value: stats.total_enrollments, color: 'success' },
  ];

  return (
    <div className="space-y-5 max-w-7xl mx-auto">
      <div className="fet-welcome-banner">
        <div className="relative z-10 flex items-center gap-3">
          <div className="w-11 h-11 rounded-xl flex items-center justify-center bg-white/10 border border-white/10">
            <AlertCircle size={22} className="text-white" />
          </div>
          <div>
            <h2 className="text-[20px] md:text-[22px] font-bold">Admin Dashboard</h2>
            <p className="text-white/50 text-[13px]">
              {stats.active_semester
                ? `Active semester: ${stats.active_semester.name}`
                : 'No active semester — registration and enrolment are closed'}
            </p>
          </div>
        </div>
      </div>

      {loadError ? (
        <div className="bg-red-50 border border-red-200 text-red-700 px-4 py-3 rounded-xl text-[13px]">
          {loadError}
        </div>
      ) : null}

      <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-3 gap-3 md:gap-4">
        {statCards.map((stat, index) => (
          <StatsCard key={index} {...stat} />
        ))}
      </div>

      <div className="fet-card p-5">
        <h3 className="text-[15px] font-semibold text-text-primary mb-4">Quick Actions</h3>
        <div className="grid grid-cols-2 gap-3">
          <button onClick={() => navigate('/admin/users')} className="flex items-center gap-2.5 p-3.5 rounded-xl bg-page-bg hover:bg-primary-light text-[13px] font-medium text-text-primary transition-colors">
            <Users size={16} className="text-primary" /> Manage Users
          </button>
          <button onClick={() => navigate('/admin/roster')} className="flex items-center gap-2.5 p-3.5 rounded-xl bg-page-bg hover:bg-primary-light text-[13px] font-medium text-text-primary transition-colors">
            <Upload size={16} className="text-primary" /> Upload Roster
          </button>
          <button onClick={() => navigate('/admin/academic')} className="flex items-center gap-2.5 p-3.5 rounded-xl bg-page-bg hover:bg-primary-light text-[13px] font-medium text-text-primary transition-colors">
            <Building2 size={16} className="text-primary" /> Semesters &amp; Departments
          </button>
          <button onClick={() => navigate('/courses')} className="flex items-center gap-2.5 p-3.5 rounded-xl bg-page-bg hover:bg-primary-light text-[13px] font-medium text-text-primary transition-colors">
            <BookOpen size={16} className="text-primary" /> Course Catalogue
          </button>
          <button onClick={() => navigate('/projects')} className="flex items-center gap-2.5 p-3.5 rounded-xl bg-page-bg hover:bg-primary-light text-[13px] font-medium text-text-primary transition-colors">
            <FolderKanban size={16} className="text-primary" /> Projects
          </button>
          <button onClick={() => navigate('/carry-over')} className="flex items-center gap-2.5 p-3.5 rounded-xl bg-page-bg hover:bg-primary-light text-[13px] font-medium text-text-primary transition-colors">
            <FilePlus2 size={16} className="text-primary" /> Carry-over Requests
          </button>
        </div>
      </div>
    </div>
  );
};

export default AdminDashboard;
