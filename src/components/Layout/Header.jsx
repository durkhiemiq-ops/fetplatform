import React, { useState, useEffect, useRef } from 'react';
import { useNavigate } from 'react-router-dom';
import {
  Search, Bell, ChevronDown, User, LogOut, Settings, CheckCheck, Moon, Sun,
} from 'lucide-react';
import { useTheme } from '../../context/ThemeContext';
import { normalizeRole } from '../../lib/profile';
import { notificationsApi } from '../../lib/notifications';
import { relativeTime } from '../../lib/format';

// The bell used to render a hardcoded three-item array seeded into
// localStorage['fet_notifications'] and never call the API, while Sidebar.jsx
// showed a real unread badge from the same endpoint -- two contradictory
// sources in one shell, and a fabricated inbox shown to every user. It now
// reads the real owner-scoped inbox (GET /notifications/?unread=true) and maps
// the server's snake_case row into the shape the panel renders.
const fromApi = (row) => ({
  id: row.id,
  title: row.title,
  category: row.category,
  read: Boolean(row.is_read),
  time: relativeTime(row.created_at),
});

const Header = ({ user, onLogout }) => {
  const navigate = useNavigate();
  const { theme, toggleTheme } = useTheme();
  const [showNotifications, setShowNotifications] = useState(false);
  const [showProfile, setShowProfile] = useState(false);
  const [notifications, setNotifications] = useState([]);
  const notifRef = useRef(null);
  const profileRef = useRef(null);

  useEffect(() => {
    let cancelled = false;
    notificationsApi
      .list()
      .then((rows) => {
        if (!cancelled) setNotifications((Array.isArray(rows) ? rows : []).map(fromApi));
      })
      .catch(() => {
        // Backend unreachable: show an empty inbox rather than fabricated data.
        if (!cancelled) setNotifications([]);
      });
    return () => { cancelled = true; };
  }, []);

  useEffect(() => {
    const handleClick = (e) => {
      if (notifRef.current && !notifRef.current.contains(e.target)) setShowNotifications(false);
      if (profileRef.current && !profileRef.current.contains(e.target)) setShowProfile(false);
    };
    document.addEventListener('mousedown', handleClick);
    return () => document.removeEventListener('mousedown', handleClick);
  }, []);

  const name = [user?.first_name, user?.last_name].filter(Boolean).join(' ') || user?.email?.split('@')[0] || 'User';
  const role = normalizeRole(user?.role || 'student');
  const initials = name.split(' ').map((n) => n[0]).join('').toUpperCase().slice(0, 2);
  const unreadCount = notifications.filter((n) => !n.read).length;

  const markAsRead = async (id) => {
    try {
      await notificationsApi.markRead(id);
      setNotifications((prev) => prev.map((n) => (n.id === id ? { ...n, read: true } : n)));
    } catch {
      // Keep the unread state when the server did not persist the mutation.
    }
  };
  const markAllAsRead = async () => {
    try {
      await notificationsApi.markAllRead();
      setNotifications((prev) => prev.map((n) => ({ ...n, read: true })));
    } catch {
      // Keep the current badge when the server rejected the mutation.
    }
  };

  const handleLogout = () => {
    // Server destroys the session; App drops the in-memory identity. Nothing
    // to clear in localStorage because nothing is cached there.
    if (onLogout) onLogout();
    else window.location.reload();
  };

  const panel = 'absolute right-0 top-full mt-2 w-80 bg-surface rounded-lg shadow-modal border border-border-default z-50 overflow-hidden';
  const menuItem = 'w-full flex items-center gap-2.5 px-4 py-2.5 text-[13px] text-text-primary hover:bg-page-bg transition-colors text-left';

  return (
    <header className="flex h-[58px] shrink-0 items-center gap-3 border-b border-border-default bg-surface px-4 md:px-6">
      <div className="relative hidden md:block max-w-[430px] flex-1">
        <Search size={15} className="absolute left-3 top-1/2 -translate-y-1/2 text-text-muted" />
        <input
          type="text"
          placeholder="Search classrooms, projects, students"
          className="fet-input pl-[34px] pr-16 text-[13px]"
          style={{ backgroundColor: 'rgb(var(--canvas))' }}
        />
        <span
          className="pointer-events-none absolute right-2 top-1/2 hidden -translate-y-1/2 items-center rounded-[4px] border border-border-default bg-surface px-1.5 text-[10px] text-text-secondary md:flex"
          style={{ height: 19, borderBottomWidth: 2 }}
        >
          Ctrl K
        </span>
      </div>

      <div className="flex-1" />

      <div className="flex items-center gap-1.5 md:gap-2">
        <button
          type="button"
          onClick={toggleTheme}
          className="grid h-9 w-9 place-items-center rounded-md border border-border-default bg-surface text-text-secondary transition-colors hover:bg-page-bg"
          aria-label={theme === 'dark' ? 'Switch to light theme' : 'Switch to dark theme'}
          title={theme === 'dark' ? 'Light theme' : 'Dark theme'}
        >
          {theme === 'dark' ? <Sun size={16} /> : <Moon size={16} />}
        </button>

        <div className="relative" ref={notifRef}>
          <button
            type="button"
            onClick={() => { setShowNotifications((v) => !v); setShowProfile(false); }}
            className="relative grid h-9 w-9 place-items-center rounded-md border border-border-default bg-surface text-text-secondary transition-colors hover:bg-page-bg"
            aria-label="Notifications"
          >
            <Bell size={16} />
            {unreadCount > 0 ? (
              <span className="absolute right-1.5 top-1.5 h-2 w-2 rounded-full bg-danger ring-2 ring-surface" />
            ) : null}
          </button>

          {showNotifications ? (
            <div className={panel}>
              <div className="flex items-center justify-between border-b border-border-default px-4 py-3">
                <p className="text-[13px] font-semibold text-text-primary">Notifications</p>
                <button
                  type="button"
                  onClick={markAllAsRead}
                  className="flex items-center gap-1 text-[12px] font-medium text-primary hover:opacity-80"
                >
                  <CheckCheck size={14} /> Mark all read
                </button>
              </div>
              <div className="max-h-72 overflow-y-auto">
                {notifications.length === 0 ? (
                  <p className="py-8 text-center text-[13px] text-text-secondary">No notifications</p>
                ) : notifications.map((n) => (
                  <button
                    key={n.id}
                    type="button"
                    onClick={() => markAsRead(n.id)}
                    className={`w-full border-b border-border-default/50 px-4 py-3 text-left transition-colors last:border-0 hover:bg-page-bg ${n.read ? '' : 'bg-primary-light/40'}`}
                  >
                    <span className="text-[10px] font-bold uppercase tracking-wider text-primary">{n.category}</span>
                    <p className="mt-0.5 text-[13px] font-medium text-text-primary">{n.title}</p>
                    <p className="mt-0.5 text-[11px] text-text-secondary">{n.time}</p>
                  </button>
                ))}
              </div>
            </div>
          ) : null}
        </div>

        <div className="relative" ref={profileRef}>
          <button
            type="button"
            onClick={() => { setShowProfile((v) => !v); setShowNotifications(false); }}
            className="flex items-center gap-2.5 rounded-md py-1 pl-1 pr-2 transition-colors hover:bg-page-bg"
            aria-label="Profile menu"
          >
            <span className="ui-avatar h-8 w-8 bg-primary text-[12px]">{initials}</span>
            <span className="hidden text-left sm:block">
              <span className="block max-w-[110px] truncate text-[13px] font-medium leading-tight text-text-primary">{name}</span>
              <span className="block text-[11px] capitalize leading-tight text-text-secondary">{role}</span>
            </span>
            <ChevronDown size={14} className="hidden text-text-secondary sm:block" />
          </button>

          {showProfile ? (
            <div className="absolute right-0 top-full mt-2 w-52 overflow-hidden rounded-lg border border-border-default bg-surface shadow-modal">
              <div className="border-b border-border-default px-4 py-3">
                <p className="text-[13px] font-semibold text-text-primary">{name}</p>
                <p className="text-[11px] capitalize text-text-secondary">{role}</p>
              </div>
              <div className="py-1">
                <button type="button" className={menuItem} onClick={() => { setShowProfile(false); navigate('/profile'); }}>
                  <User size={15} /> Profile
                </button>
                <button type="button" className={menuItem} onClick={() => { setShowProfile(false); navigate('/settings'); }}>
                  <Settings size={15} /> Settings
                </button>
                <div className="mx-3 my-1 h-px bg-border-default" />
                <button
                  type="button"
                  onClick={handleLogout}
                  className="flex w-full items-center gap-2.5 px-4 py-2.5 text-[13px] text-danger transition-colors hover:bg-red-50"
                >
                  <LogOut size={15} /> Sign out
                </button>
              </div>
            </div>
          ) : null}
        </div>
      </div>
    </header>
  );
};

export default Header;
