import React from 'react';
import StudentDashboard from './StudentDashboard';
import LecturerDashboard from './LecturerDashboard';
import CoordinatorDashboard from './CoordinatorDashboard';

/**
 * Routes to the role-appropriate dashboard.
 *
 * C2: the user and role now come from props (populated from the authenticated
 * session in App.jsx). This previously parsed localStorage, which anyone can
 * edit in devtools — a student could claim the lecturer dashboard.
 */
const DashboardHome = ({ user }) => {
  const role = user?.role || 'student';

  if (role === 'coordinator') {
    return <CoordinatorDashboard user={user} />;
  } else if (role === 'lecturer' || role === 'admin') {
    return <LecturerDashboard user={user} />;
  } else {
    return <StudentDashboard user={user} />;
  }
};

export default DashboardHome;
