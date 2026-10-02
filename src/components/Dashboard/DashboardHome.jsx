import React from 'react';
import StudentDashboard from './StudentDashboard';
import LecturerDashboard from './LecturerDashboard';
import CoordinatorDashboard from './CoordinatorDashboard';
import AdminDashboard from '../../Pages/Admin/AdminDashboard';
import { useSession } from '../../context/SessionContext';

const DashboardHome = () => {
  // Dispatch on the verified session role, not localStorage. `COORDINATOR` is
  // not a backend User.Role value, so the coordinator branch is unreachable
  // dead UI; it is kept only until that role is actually implemented.
  const { role, user } = useSession();

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
