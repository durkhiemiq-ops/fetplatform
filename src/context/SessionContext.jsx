/**
 * Session context — the verified identity every component should read.
 *
 * Why this exists
 * ---------------
 * AGENTS.md requires that identity, roles, and permissions come from the
 * verified server session, never from browser storage. Before this, eight
 * components read the role from `localStorage['fet_user_role']` at render
 * time, which any user can edit in DevTools. That is fine as a *cache* but
 * wrong as the *authority* for what the UI is allowed to show.
 *
 * `App` populates this once, immediately after a successful `GET /auth/me/`
 * against the httpOnly session cookie. From then on, `useSession()` is the one
 * source of truth for "who am I and what may I see".
 *
 * This is deliberately NOT the phantom `useAppContext()` the old AGENTS.md
 * mandated (with a `utils/mappers.js` that never existed). It is scoped
 * narrowly to session identity + a handful of derived role helpers, uses the
 * snake_case wire fields directly as AGENTS.md requires, and leaves data
 * fetching in the existing `lib/*.js` clients.
 */

import React, { createContext, useContext, useMemo } from 'react';

/** Map a backend User.Role value onto the UI's lowercase role vocabulary. */
export const normalizeRole = (role) => {
  const r = (role || '').toLowerCase();
  if (r === 'student' || r === 'lecturer') return r;
  // Backend emits 'ADMINISTRATOR'. The old `r.endsWith('_admin')` check was
  // false for 'administrator', which locked every real admin out of /admin/*.
  if (r === 'admin' || r === 'administrator' || r.endsWith('_admin')) return 'admin';
  return r || 'student';
};

const SessionContext = createContext({
  user: null,
  role: 'student',
  isAuthenticated: false,
  isAdmin: false,
  isStaff: false,
  isStudent: false,
  userName: 'User',
  initials: 'U',
});

export const SessionProvider = ({ user, isAuthenticated, children }) => {
  const value = useMemo(() => {
    const role = normalizeRole(user?.role || 'student');
    const userName = user?.full_name || user?.fullName || user?.email?.split('@')[0] || 'User';
    return {
      user,
      role,
      isAuthenticated: Boolean(isAuthenticated),
      isAdmin: role === 'admin',
      isStaff: role === 'admin' || role === 'lecturer',
      isStudent: role === 'student',
      userName,
      initials: userName
        .split(' ')
        .map((n) => n[0])
        .join('')
        .toUpperCase()
        .slice(0, 2),
    };
  }, [user, isAuthenticated]);

  return <SessionContext.Provider value={value}>{children}</SessionContext.Provider>;
};

export const useSession = () => useContext(SessionContext);

export default SessionContext;