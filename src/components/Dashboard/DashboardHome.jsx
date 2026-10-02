import React from 'react';
import StudentDashboard from './StudentDashboard';
import LecturerDashboard from './LecturerDashboard';
import CoordinatorDashboard from './CoordinatorDashboard';
import AdminDashboard from '../../Pages/Admin/AdminDashboard';
import { normalizeRole } from '../../lib/profile';

const DashboardHome = () => {
  const user = JSON.parse(localStorage.getItem('fet_user') || '{}');
  const role = normalizeRole(user?.role || localStorage.getItem('fet_user_role'));

  if (role === 'admin') {
    return <AdminDashboard user={user} />;
  }
  if (role === 'coordinator') {
    return <CoordinatorDashboard user={user} />;
  }
  if (role === 'lecturer') {
    return <LecturerDashboard user={user} />;
  }
  return <StudentDashboard user={user} />;
};

export default DashboardHome;
