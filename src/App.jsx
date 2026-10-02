import React, { useState, useEffect } from 'react';
import { BrowserRouter as Router, Routes, Route, Navigate } from 'react-router-dom';
import { AppProvider, useAppContext } from './context/AppContext';
import Sidebar from './components/Layout/Sidebar';
import Header from './components/Layout/Header';
import DashboardHome from './components/Dashboard/DashboardHome';
import StudentDashboard from './components/Dashboard/StudentDashboard';
import LecturerDashboard from './components/Dashboard/LecturerDashboard';
import CoordinatorDashboard from './components/Dashboard/CoordinatorDashboard';
import Login from './components/Auth/Login';
import SignUp from './components/Auth/SignUp';
import VerifyEmail from './components/Auth/VerifyEmail';
import ProfilePage from './components/Profile/ProfilePage';
import CourseCatalogue from './Pages/Courses/CourseCatalogue';
import AttendanceDashboard from './components/Attendance/AttendanceDashboard';
import ProjectsList from './components/Projects/ProjectsList';
import ProjectDetails from './components/Projects/ProjectDetails';
import TaskList from './components/Tasks/TaskList';
import GroupList from './components/Groups/GroupList';
import ContinuousAssessment from './components/Assessment/ContinuousAssessment';
import ContributionTracking from './components/Assessment/ContributionTracking';
import ContributionsPage from './components/Contributions/ContributionsPage';
import AnnouncementList from './components/Announcements/AnnouncementList';
import AcademicCalendar from './components/Academic/AcademicCalender';
import AdminDashboard from './Pages/Admin/AdminDashboard';
import AdminUsers from './Pages/Admin/AdminUser';
import MobileSimulator from './components/Mobile/MobileSimulator';
import { login as apiLogin, register as apiRegister, getCurrentUser, logout as apiLogout } from './api/auth';
import { setSessionExpiredHandler } from './api/client';
import { normalizeRole } from './utils/tokenHelpers';

/**
 * Map the backend user (Uppercase role, first/last name) to the display shape
 * Attendî's components consume. The backend role stays the source of truth;
 * `role` is the client-normalized view of it (BR-003).
 */
function toDisplayUser(backendUser) {
  const role = normalizeRole(backendUser.role);
  return {
    ...backendUser,
    id: backendUser.id,
    email: backendUser.email,
    matricule: backendUser.matricule || '',
    fullName: `${backendUser.first_name} ${backendUser.last_name}`.trim() || backendUser.username,
    role,
  };
}

/**
 * Route guard. C2: authorization is derived from the authenticated user held in
 * React state (populated from GET /accounts/me/ and the login response), NOT
 * from localStorage — anyone can edit localStorage in devtools, so reading a
 * role from there grants nothing but the illusion of access. The backend still
 * enforces every rule; this only stops a student rendering an admin shell.
 */
const RequireRole = ({ role, user, children }) => {
  if (!user || user.role !== role) return <Navigate to="/" replace />;
  return children;
};

function App() {
  const [isAuthenticated, setIsAuthenticated] = useState(false);
  const [user, setUser] = useState(null);
  const [showSignUp, setShowSignUp] = useState(false);
  const [isLoading, setIsLoading] = useState(true);
  // {email, password} held in memory only while the OTP screen is up.
  const [pendingVerify, setPendingVerify] = useState(null);

  // M2: session expiry is handled in-app. The API client calls this when the
  // backend reports UNAUTHENTICATED, so we drop to the login screen without a
  // full page reload (which would discard the in-memory OTP credentials).
  useEffect(() => {
    setSessionExpiredHandler(() => {
      setIsAuthenticated(false);
      setUser(null);
      setPendingVerify(null);
    });
    return () => setSessionExpiredHandler(null);
  }, []);

  // Restore the session from the backend cookie on mount.
  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        const me = await getCurrentUser();
        if (!cancelled) {
          setUser(toDisplayUser(me));
          setIsAuthenticated(true);
        }
      } catch {
        if (!cancelled) {
          setIsAuthenticated(false);
          setUser(null);
        }
      } finally {
        if (!cancelled) setIsLoading(false);
      }
    })();
    return () => { cancelled = true; };
  }, []);

  const handleLogin = async (identifier, password) => {
    try {
      const backendUser = await apiLogin({ identifier, password });
      const mapped = toDisplayUser(backendUser);
      setIsAuthenticated(true);
      setUser(mapped);
      return { success: true };
    } catch (err) {
      // Verification gate: park credentials in memory and show the OTP screen.
      if (err.code === 'ACCOUNT_NOT_VERIFIED') {
        setPendingVerify({ email: identifier, password });
        return { success: false, code: err.code };
      }
      return { success: false, message: err.message || 'Login failed' };
    }
  };

  const handleSignUp = async (form) => {
    try {
      const nameParts = (form.fullName || '').trim().split(/\s+/);
      const firstName = nameParts[0] || '';
      const lastName = nameParts.slice(1).join(' ') || firstName;
      await apiRegister({
        email: form.email.toLowerCase(),
        username: form.email.split('@')[0],
        first_name: firstName,
        last_name: lastName,
        password: form.password,
      });
      // Registration never logs in (BR-002 + the email gate).
      setPendingVerify({ email: form.email.toLowerCase(), password: form.password });
      return { success: true };
    } catch (err) {
      return { success: false, message: err.message || 'Registration failed' };
    }
  };

  const handleVerified = async () => {
    const res = await handleLogin(pendingVerify.email, pendingVerify.password);
    if (res.success) setPendingVerify(null);
    return res;
  };

  const handleLogout = async () => {
    try {
      await apiLogout();
    } catch {
      // The session may already be gone; clear client state regardless.
    }
    setIsAuthenticated(false);
    setUser(null);
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

  if (pendingVerify) {
    return (
      <VerifyEmail
        email={pendingVerify.email}
        onVerified={handleVerified}
        onCancel={() => setPendingVerify(null)}
      />
    );
  }

  if (!isAuthenticated) {
    if (showSignUp) {
      return <SignUp onSignUp={handleSignUp} onSwitchToLogin={() => setShowSignUp(false)} />;
    }
    return <Login onLogin={handleLogin} onSwitchToSignUp={() => setShowSignUp(true)} />;
  }

  const userName = user?.fullName || 'User';
  const userRole = user?.role || 'student';

  return (
    <AppProvider user={user}>
      <Router>
        <div className="app-container flex h-screen bg-page-bg">
          <Sidebar onLogout={handleLogout} userName={userName} userRole={userRole} />
          <div className="flex-1 flex flex-col overflow-hidden min-w-0">
            <Header user={user} onLogout={handleLogout} />
            <main className="flex-1 overflow-y-auto p-4 md:p-6">
              {/*
                A partial-load failure must be visible, not silently empty (C1).
                The shell stays usable; the banner explains what is missing.
              */}
              <LoadErrorBanner />
              <Routes>
                <Route path="/" element={<DashboardHome user={user} />} />
                <Route path="/dashboard" element={<DashboardHome user={user} />} />
                <Route path="/student-dashboard" element={<StudentDashboard user={user} />} />
                <Route path="/lecturer-dashboard" element={<LecturerDashboard user={user} />} />
                <Route path="/coordinator-dashboard" element={<CoordinatorDashboard user={user} />} />
                <Route path="/profile" element={<ProfilePage user={user} />} />
                <Route path="/courses" element={<CourseCatalogue user={user} />} />
                <Route path="/attendance" element={<AttendanceDashboard user={user} />} />
                <Route path="/projects" element={<ProjectsList user={user} />} />
                <Route path="/projects/:id" element={<ProjectDetails user={user} />} />
                <Route path="/tasks" element={<TaskList user={user} />} />
                <Route path="/groups" element={<GroupList user={user} />} />
                <Route path="/assessment" element={<ContinuousAssessment user={user} />} />
                <Route path="/contribution" element={<ContributionsPage user={user} />} />
                <Route
                  path="/contribution/tracking"
                  element={
                    <RequireRole role="lecturer" user={user}>
                      <ContributionTracking user={user} />
                    </RequireRole>
                  }
                />
                <Route path="/announcements" element={<AnnouncementList user={user} />} />
                <Route path="/academic" element={<AcademicCalendar />} />
                <Route path="/mobile-simulator" element={<MobileSimulator />} />
                <Route
                  path="/admin/dashboard"
                  element={
                    <RequireRole role="admin" user={user}>
                      <AdminDashboard user={user} />
                    </RequireRole>
                  }
                />
                <Route
                  path="/admin/users"
                  element={
                    <RequireRole role="admin" user={user}>
                      <AdminUsers user={user} />
                    </RequireRole>
                  }
                />
                <Route
                  path="/admin/attendance"
                  element={
                    <RequireRole role="admin" user={user}>
                      <AttendanceDashboard user={user} />
                    </RequireRole>
                  }
                />
                <Route path="*" element={<Navigate to="/" />} />
              </Routes>
            </main>
          </div>
        </div>
      </Router>
    </AppProvider>
  );
}

/** Renders the AppContext load error so a partial failure is never silent. */
function LoadErrorBanner() {
  const { error, loading } = useAppContext();
  if (loading || !error) return null;
  return (
    <div className="mb-4 rounded-lg border border-amber-300 bg-amber-50 px-4 py-3 text-[13px] text-amber-900">
      <strong>Some data could not be loaded.</strong> {error}
    </div>
  );
}

export default App;
