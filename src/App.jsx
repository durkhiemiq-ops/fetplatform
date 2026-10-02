import React, { useState, useEffect } from 'react';
import { BrowserRouter as Router, Routes, Route, Navigate } from 'react-router-dom';
import { ThemeProvider } from './context/ThemeContext';
import { SessionProvider, useSession } from './context/SessionContext';
import Sidebar from './components/Layout/Sidebar';
import Header from './components/Layout/Header';
import DashboardHome from './components/Dashboard/DashboardHome';
import StudentDashboard from './components/Dashboard/StudentDashboard';
import LecturerDashboard from './components/Dashboard/LecturerDashboard';
import CoordinatorDashboard from './components/Dashboard/CoordinatorDashboard';
import Login from './components/Auth/Login';
import ChangePassword from './components/Auth/ChangePassword';
import ProfilePage from './components/Profile/ProfilePage';
import AttendanceDashboard from './components/Attendance/AttendanceDashboard';
import ProjectsList from './components/Projects/ProjectsList';
import ProjectDetails from './components/Projects/ProjectDetails';
import ContinuousAssessment from './components/Assessment/ContinuousAssessment';
import ContributionTracking from './components/Assessment/ContributionTracking';
import AnnouncementList from './components/Announcements/AnnouncementList';
import AcademicCalendar from './components/Academic/AcademicCalender';
import AcademicSetup from './components/Academic/AcademicSetup';
import Timetable from './components/Academic/Timetable';
import CarryOverPage from './components/Academic/CarryOverPage';
import NotificationList from './components/Notifications/NotificationList';
import RosterUpload from './components/Admin/RosterUpload';
import AuditLogConsole from './components/Admin/AuditLogConsole';
import RegistrationPage from './Pages/Courses/RegistrationPage';
import AdminDashboard from './Pages/Admin/AdminDashboard';
import MobileSimulator from './components/Mobile/MobileSimulator';
import MyCourses from './Pages/Lessons/MyCourses';
import CourseDetail from './Pages/Lessons/CourseDetail';
import { authApi } from './lib/auth';

// Route guards read the verified session (populated from GET /auth/me/ after a
// successful session-cookie check), not localStorage. These are a UI
// convenience only: the backend remains the sole enforcement point, per
// AGENTS.md and BR-003.
const RequireRole = ({ role, children }) => {
  const { role: currentRole } = useSession();
  if (currentRole !== role) return <Navigate to="/" replace />;
  return children;
};

const ExcludeRole = ({ role, children }) => {
  const { role: currentRole } = useSession();
  if (currentRole === role) return <Navigate to="/lessons" replace />;
  return children;
};

// Everything a fully-provisioned account can reach.
const DashboardRoutes = ({ user }) => (
  <Routes>
    <Route path="/" element={<DashboardHome />} />
    <Route path="/dashboard" element={<DashboardHome />} />
    <Route path="/student-dashboard" element={<StudentDashboard user={user} />} />
    <Route path="/lecturer-dashboard" element={<LecturerDashboard user={user} />} />
    <Route path="/coordinator-dashboard" element={<CoordinatorDashboard user={user} />} />
    <Route path="/profile" element={<ProfilePage user={user} />} />
    <Route path="/lessons" element={<MyCourses user={user} />} />
    <Route path="/lessons/:offeringId" element={<CourseDetail user={user} />} />
    <Route path="/attendance" element={<AttendanceDashboard user={user} />} />
    <Route path="/projects" element={<ProjectsList />} />
    <Route path="/projects/:id" element={<ProjectDetails />} />
    <Route path="/assessment" element={<ContinuousAssessment user={user} />} />
    <Route
      path="/contribution/tracking"
      element={<RequireRole role="lecturer"><ContributionTracking user={user} /></RequireRole>}
    />
    <Route path="/announcements" element={<AnnouncementList user={user} />} />
    <Route path="/notifications" element={<NotificationList />} />
    <Route path="/timetable" element={<Timetable />} />
    <Route path="/carry-over" element={<CarryOverPage user={user} />} />
    <Route
      path="/register"
      element={<RequireRole role="student"><RegistrationPage /></RequireRole>}
    />
    <Route path="/academic" element={<AcademicCalendar />} />
    <Route path="/mobile-simulator" element={<MobileSimulator />} />
    <Route path="/settings" element={<ProfilePage user={user} />} />
    <Route
      path="/admin/dashboard"
      element={<RequireRole role="admin"><AdminDashboard user={user} /></RequireRole>}
    />
    <Route
      path="/admin/academic"
      element={<RequireRole role="admin"><AcademicSetup /></RequireRole>}
    />
    <Route
      path="/admin/audit"
      element={<RequireRole role="admin"><AuditLogConsole /></RequireRole>}
    />
    <Route
      path="/admin/roster"
      element={<RequireRole role="admin"><RosterUpload /></RequireRole>}
    />
    {/* Mock pages removed. Their live equivalents already exist, so
        old links land somewhere real instead of the catch-all. */}
    <Route path="/tasks" element={<Navigate to="/projects" replace />} />
    <Route path="/groups" element={<Navigate to="/projects" replace />} />
    <Route path="/contribution" element={<Navigate to="/projects" replace />} />
    <Route path="/courses" element={<Navigate to="/lessons" replace />} />
    <Route path="/admin/users" element={<Navigate to="/admin/roster" replace />} />
    <Route path="*" element={<Navigate to="/" />} />
  </Routes>
);

function App() {
  const [isAuthenticated, setIsAuthenticated] = useState(false);
  const [user, setUser] = useState(null);
  const [isLoading, setIsLoading] = useState(true);

  useEffect(() => {
    const initAuth = async () => {
      try {
        // Session is validated against the backend using httpOnly cookies.
        const response = await authApi.me();
        const userData = response.data?.data ?? response.data;
        setUser(userData);
        setIsAuthenticated(true);
      } catch (error) {
        // No valid session (or refresh failed) — show login. Identity is not
        // cached in localStorage; the httpOnly session cookie is the only
        // thing that decides whether this branch runs (AGENTS.md).
        setUser(null);
        setIsAuthenticated(false);
      }
      setIsLoading(false);
    };
    initAuth();
  }, []);

  // Identity lives in React state + SessionProvider now, not localStorage.
// ProfilePage re-reads the authoritative record itself after saving, so there
// is nothing to listen for on a profile change.
useEffect(() => {
    const onExpired = () => {
      setIsAuthenticated(false);
      setUser(null);
    };
    window.addEventListener('fet-session-expired', onExpired);
    return () => window.removeEventListener('fet-session-expired', onExpired);
  }, []);

  const handleLogin = (userData) => {
    setIsAuthenticated(true);
    setUser(userData);
  };

  const handleLogout = async () => {
    try {
      await authApi.logout();
    } catch (error) {
      console.error('Logout error:', error);
    } finally {
      setIsAuthenticated(false);
      setUser(null);
    }
  };

  if (isLoading) {
    return (
      <div className="min-h-screen flex items-center justify-center bg-page-bg">
        <div className="text-center">
          <div className="w-12 h-12 rounded-xl flex items-center justify-center mx-auto mb-4" style={{ backgroundColor: '#3F35B5' }}>
            <span className="text-white font-bold text-lg">FET</span>
          </div>
          <div className="w-8 h-8 border-[3px] border-primary border-t-transparent rounded-full animate-spin mx-auto"></div>
          <p className="mt-3 text-[13px] text-text-secondary font-medium">Loading...</p>
        </div>
      </div>
    );
  }

  if (!isAuthenticated) {
    return <Login onLogin={handleLogin} />;
  }

  return (
    <SessionProvider user={user} isAuthenticated={isAuthenticated}>
      <ThemeProvider>
        <Router>
          <Shell user={user} onLogout={handleLogout} />
        </Router>
      </ThemeProvider>
    </SessionProvider>
  );
}

// Split out so it renders *inside* SessionProvider and can call useSession().
function Shell({ user, onLogout }) {
  const { userName, role } = useSession();

  return (
    <div className="app-container flex h-screen bg-page-bg">
      <Sidebar onLogout={onLogout} userName={userName} userRole={role} />
      <div className="flex min-w-0 flex-1 flex-col overflow-hidden">
        <Header user={user} onLogout={onLogout} />
        <main className="flex-1 overflow-y-auto p-4 md:p-6">
          <Routes>
            <Route path="/change-password" element={<ChangePassword user={user} />} />
            <Route path="*" element={<DashboardRoutes user={user} />} />
          </Routes>
        </main>
      </div>
    </div>
  );
}

export default App;
