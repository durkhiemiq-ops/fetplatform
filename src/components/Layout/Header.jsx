import React, { useState, useEffect, useRef } from 'react';
import { useNavigate } from 'react-router-dom';
import { Search, Bell, ChevronDown, User, School, LogOut, Settings, CheckCheck, X } from 'lucide-react';
import { getNotifications, markNotificationRead, markAllNotificationsRead } from '../../api/notifications';

/** Map backend notification row to the header's display shape. */
const toDisplayNotification = (n) => ({
  id: n.id,
  title: n.title,
  body: n.body,
  category: (n.category || 'general').replace(/_/g, ' '),
  time: n.created_at ? new Date(n.created_at).toLocaleString() : '',
  read: Boolean(n.is_read),
});

const Header = ({ user, onLogout }) => {
  const navigate = useNavigate();
  const [showNotifications, setShowNotifications] = useState(false);
  const [showProfile, setShowProfile] = useState(false);
  const [notifications, setNotifications] = useState([]);
  const notifRef = useRef(null);
  const profileRef = useRef(null);

  // Load the authenticated user's inbox from the API on mount.
  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        const rows = await getNotifications();
        if (!cancelled) setNotifications(rows.map(toDisplayNotification));
      } catch {
        // Non-fatal: the inbox stays empty until the next login/poll.
      }
    })();
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

  const name = user?.fullName || 'User';
  const role = user?.role || 'student';
  const initials = name.split(' ').map(n => n[0]).join('').toUpperCase().slice(0, 2);

  const unreadCount = notifications.filter(n => !n.read).length;

  const markAsRead = async (id) => {
    setNotifications(prev => prev.map(n => n.id === id ? { ...n, read: true } : n));
    try { await markNotificationRead(id); } catch { /* idempotent on the server */ }
  };

  const markAllAsRead = async () => {
    setNotifications(prev => prev.map(n => ({ ...n, read: true })));
    try { await markAllNotificationsRead(); } catch { /* server stays authoritative */ }
  };

  const handleLogout = () => {
    if (onLogout) onLogout();
    else window.location.reload();
  };

  const roleColor = role === 'admin' ? '#DC2626' : role === 'lecturer' ? '#3F35B5' : '#2563EB';

  return (
    <header className="bg-white border-b border-border-default px-4 md:px-6 py-3 flex items-center justify-between">
      {/* Left - Search */}
      <div className="hidden md:flex relative flex-1 max-w-md">
        <Search className="absolute left-3 top-1/2 transform -translate-y-1/2 text-text-secondary" size={16} strokeWidth={2} />
        <input
          type="text"
          placeholder="Search courses, projects, tasks..."
          className="fet-input pl-10 pr-4 py-2.5 text-[13px]"
          style={{ backgroundColor: '#F6F7FB', border: '1px solid transparent' }}
        />
      </div>

      {/* Mobile Title */}
      <div className="lg:hidden flex items-center gap-2 pl-10">
        <div className="w-7 h-7 rounded-lg flex items-center justify-center" style={{ backgroundColor: '#3F35B5' }}>
          <span className="text-white font-bold text-[10px]">FET</span>
        </div>
        <span className="text-[14px] font-bold text-text-primary">FET</span>
      </div>

      {/* Right - Actions */}
      <div className="flex items-center gap-1 md:gap-2">
        {/* Search icon on mobile */}
        <button className="lg:hidden p-2 rounded-lg hover:bg-page-bg transition-colors" aria-label="Search">
          <Search size={18} className="text-text-secondary" strokeWidth={2} />
        </button>

        {/* Notifications */}
        <div className="relative" ref={notifRef}>
          <button
            onClick={() => { setShowNotifications(!showNotifications); setShowProfile(false); }}
            className="relative p-2.5 rounded-xl hover:bg-page-bg transition-colors"
            aria-label="Notifications"
          >
            <Bell size={18} className="text-text-secondary" strokeWidth={2} />
            {unreadCount > 0 && (
              <span className="absolute top-1.5 right-1.5 w-[18px] h-[18px] bg-danger text-white text-[10px] font-bold rounded-full flex items-center justify-center">
                {unreadCount}
              </span>
            )}
          </button>

          {showNotifications && (
            <div className="absolute right-0 top-full mt-2 w-80 bg-white rounded-2xl shadow-dropdown border border-border-default z-50 overflow-hidden">
              <div className="px-4 py-3 flex items-center justify-between border-b border-border-default">
                <p className="font-semibold text-text-primary text-[14px]">Notifications</p>
                <button
                  onClick={markAllAsRead}
                  className="flex items-center gap-1 text-[12px] text-primary font-medium hover:opacity-80 transition-opacity"
                >
                  <CheckCheck size={14} /> Mark all read
                </button>
              </div>
              <div className="max-h-72 overflow-y-auto">
                {notifications.length === 0 && (
                  <p className="text-center text-text-secondary py-8 text-[13px]">No notifications</p>
                )}
                {notifications.map(n => (
                  <button
                    key={n.id}
                    onClick={() => markAsRead(n.id)}
                    className={`w-full text-left px-4 py-3 border-b border-border-default/50 last:border-0 hover:bg-page-bg transition-colors ${!n.read ? 'bg-primary-light/30' : ''}`}
                  >
                    <span className="text-[10px] uppercase tracking-wider text-primary font-bold">{n.category}</span>
                    <p className="text-[13px] text-text-primary mt-0.5 font-medium">{n.title}</p>
                    <p className="text-[11px] text-text-secondary mt-0.5">{n.time}</p>
                  </button>
                ))}
              </div>
            </div>
          )}
        </div>

        {/* Profile */}
        <div className="relative" ref={profileRef}>
          <button
            onClick={() => { setShowProfile(!showProfile); setShowNotifications(false); }}
            className="flex items-center gap-2.5 pl-3 pr-2 py-1.5 rounded-xl hover:bg-page-bg transition-colors"
            aria-label="Profile menu"
          >
            <div className="w-8 h-8 rounded-lg flex items-center justify-center font-bold text-white text-[12px]" style={{ backgroundColor: roleColor }}>
              {initials}
            </div>
            <div className="hidden sm:block text-left">
              <p className="text-[13px] font-semibold text-text-primary leading-tight truncate max-w-[100px]">{name}</p>
              <p className="text-[11px] text-text-secondary capitalize">{role}</p>
            </div>
            <ChevronDown size={14} className="text-text-secondary hidden sm:block" />
          </button>

          {showProfile && (
            <div className="absolute right-0 top-full mt-2 w-52 bg-white rounded-2xl shadow-dropdown border border-border-default z-50 overflow-hidden">
              <div className="px-4 py-3 border-b border-border-default">
                <p className="font-semibold text-text-primary text-[13px]">{name}</p>
                <p className="text-[11px] text-text-secondary capitalize">{role}</p>
              </div>
              <div className="py-1">
                <button
                  onClick={() => { setShowProfile(false); navigate('/profile'); }}
                  className="w-full flex items-center gap-2.5 px-4 py-2.5 text-[13px] hover:bg-page-bg transition-colors text-text-primary"
                >
                  <User size={15} strokeWidth={2} /> Profile
                </button>
                <button
                  onClick={() => { setShowProfile(false); navigate('/academic'); }}
                  className="w-full flex items-center gap-2.5 px-4 py-2.5 text-[13px] hover:bg-page-bg transition-colors text-text-primary"
                >
                  <School size={15} strokeWidth={2} /> Academic
                </button>
                <button
                  onClick={() => { setShowProfile(false); navigate('/profile'); }}
                  className="w-full flex items-center gap-2.5 px-4 py-2.5 text-[13px] hover:bg-page-bg transition-colors text-text-primary"
                >
                  <Settings size={15} strokeWidth={2} /> Settings
                </button>
                <div className="mx-3 my-1 h-px bg-border-default"></div>
                <button
                  onClick={handleLogout}
                  className="w-full flex items-center gap-2.5 px-4 py-2.5 text-[13px] text-danger hover:bg-red-50 transition-colors"
                >
                  <LogOut size={15} strokeWidth={2} /> Logout
                </button>
              </div>
            </div>
          )}
        </div>
      </div>
    </header>
  );
};

export default Header;
