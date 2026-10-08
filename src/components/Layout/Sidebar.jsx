import React, { useState, useEffect } from 'react';
import { NavLink } from 'react-router-dom';
import {
  LayoutDashboard, BookOpen, ClipboardCheck, FolderKanban, Megaphone,
  UserCircle, Settings, LogOut, Menu, X, BarChart3,
  CalendarDays, ChevronRight, Bell, BookPlus, CalendarClock, FilePlus2,
  Upload, Building2, KeyRound, ShieldCheck, UserCheck, GraduationCap,
} from 'lucide-react';
import { normalizeRole } from '../../lib/profile';
import { notificationsApi } from '../../lib/notifications';
import { IconTile } from '../UI';

/* Four areas, one colour each. This is what makes the nav scannable. */
const WORKSPACE = [
  { path: '/dashboard', icon: LayoutDashboard, label: 'Dashboard', area: 'hub' },
  { path: '/lessons', icon: BookOpen, label: 'Classrooms', area: 'classrooms' },
  { path: '/attendance', icon: ClipboardCheck, label: 'Attendance', area: 'attendance' },
  { path: '/projects', icon: FolderKanban, label: 'Projects', area: 'projects' },
  { path: '/announcements', icon: Megaphone, label: 'Announcements', area: 'announcements' },
  { path: '/notifications', icon: Bell, label: 'Notifications', area: 'hub' },
];

const ACCOUNT = [
  { path: '/profile', icon: UserCircle, label: 'Profile', area: 'hub' },
  { path: '/change-password', icon: KeyRound, label: 'Change password', area: 'hub' },
  { path: '/settings', icon: Settings, label: 'Settings', area: 'hub' },
];

/* Still fully working screens that simply do not deserve top level billing.
   They stay reachable here rather than being deleted or redirected away. */
const MORE = [
  { path: '/assessment', icon: ClipboardCheck, label: 'Assessment', area: 'classrooms' },
  { path: '/timetable', icon: CalendarClock, label: 'Timetable', area: 'classrooms' },
  { path: '/carry-over', icon: FilePlus2, label: 'Carry-over', area: 'classrooms' },
  { path: '/register', icon: BookPlus, label: 'Register courses', area: 'classrooms', roles: ['student'] },
  { path: '/register/curriculum', icon: GraduationCap, label: 'Curriculum registration', area: 'classrooms', roles: ['student'] },
  { path: '/academic', icon: CalendarDays, label: 'Academic calendar', area: 'hub' },
];

/* Admin keeps its own places, but the four core areas stay identical so the
   product does not change shape depending on who is signed in. */
const ADMIN_ONLY = [
  { path: '/admin/dashboard', icon: LayoutDashboard, label: 'Admin dashboard', area: 'hub' },
  { path: '/admin/roster', icon: Upload, label: 'Roster upload', area: 'hub' },
  { path: '/admin/lecturers', icon: UserCheck, label: 'Lecturer approvals', area: 'hub' },
  { path: '/admin/audit', icon: ShieldCheck, label: 'Audit log', area: 'hub' },
  { path: '/admin/academic', icon: Building2, label: 'Academic setup', area: 'hub' },
];

/** An item with `roles` only shows for those roles; without it, it shows for all. */
const visibleTo = (items, role) =>
  items.filter((item) => !item.roles || item.roles.includes(role));


const Sidebar = ({ onLogout, userName = 'User', userRole = 'student' }) => {
  const [open, setOpen] = useState(false);
  const [moreOpen, setMoreOpen] = useState(false);
  const role = normalizeRole(userRole);
  const initials = userName.split(' ').map((n) => n[0]).join('').toUpperCase().slice(0, 2);

  const moreItems = visibleTo(MORE, role);

  // Real unread count, so the badge means something. The backend raises these
  // on its own (attendance checkpoints, marks), so this is not a client cache.
  const [unread, setUnread] = useState(0);
  useEffect(() => {
    let cancelled = false;
    const load = async () => {
      try {
        const list = await notificationsApi.list(true);
        if (!cancelled) setUnread((list || []).length);
      } catch {
        /* a missing badge must never break the nav */
      }
    };
    load();
    const onRead = () => load();
    window.addEventListener('fet-notifications-changed', onRead);
    return () => {
      cancelled = true;
      window.removeEventListener('fet-notifications-changed', onRead);
    };
  }, []);

  useEffect(() => {
    document.body.style.overflow = open ? 'hidden' : '';
    return () => { document.body.style.overflow = ''; };
  }, [open]);

  const close = () => setOpen(false);

  return (
    <>
      <button
        type="button"
        onClick={() => setOpen(true)}
        className="fet-mobile-only fixed left-4 top-3 z-[70] grid h-10 w-10 place-items-center rounded-md border border-border-default bg-surface shadow-card"
        aria-label="Open navigation"
      >
        <Menu size={19} className="text-text-secondary" />
      </button>

      {open && (
        <div
          className="fet-mobile-only fixed inset-0 z-[65] bg-black/50 backdrop-blur-[1px]"
          onClick={close}
          aria-hidden="true"
        />
      )}

      <aside
        className={[
          'sidebar text-white flex flex-col fixed lg:sticky top-0 h-screen z-[68]',
          'w-[258px] shrink-0 transition-transform duration-200',
          open ? 'translate-x-0 shadow-modal' : '-translate-x-full lg:translate-x-0',
        ].join(' ')}
      >
        <div className="flex flex-col h-full">
          <div className="flex items-center gap-[11px] px-[18px] pt-[18px] pb-4">
            <div className="grid h-[34px] w-[34px] place-items-center rounded-[9px] bg-primary text-[11.5px] font-bold tracking-[.04em]">
              FET
            </div>
            <div className="min-w-0">
              <div className="text-[14.5px] font-semibold leading-tight tracking-[-.01em]">FET Platform</div>
              <div className="text-[10.5px] text-white/40 leading-tight">Engineering Management</div>
            </div>
            <button
              type="button"
              onClick={close}
              className="fet-mobile-only ml-auto grid h-9 w-9 place-items-center rounded-md text-white/60 hover:bg-white/10"
              aria-label="Close navigation"
            >
              <X size={18} />
            </button>
          </div>

          <div className="mx-3 mb-3 flex items-center gap-2.5 rounded-md border border-white/5 bg-white/5 px-2.5 py-2.5">
            <div className="grid h-[31px] w-[31px] shrink-0 place-items-center rounded-full border border-white/10 bg-white/10 text-[11px] font-semibold">
              {initials || 'U'}
            </div>
            <div className="min-w-0">
              <div className="truncate text-[12.5px] font-medium text-white">{userName}</div>
              <div className="text-[10.5px] capitalize text-white/40">{role}</div>
            </div>
          </div>

          <nav className="flex-1 overflow-y-auto px-[11px] pb-2" style={{ scrollbarWidth: 'thin' }}>
            <div className="nav-section-label">Workspace</div>
            {WORKSPACE.map((item) => (
              <NavItem
                key={item.path}
                item={item}
                onNavigate={close}
                badge={item.path === '/notifications' ? unread : 0}
              />
            ))}

            {role === 'admin' ? (
              <>
                <div className="nav-section-label">Administration</div>
                {ADMIN_ONLY.map((item) => (
                  <NavItem key={item.path} item={item} onNavigate={close} />
                ))}
              </>
            ) : null}

            <div className="nav-section-label">Account</div>
            {ACCOUNT.map((item) => (
              <NavItem key={item.path} item={item} onNavigate={close} />
            ))}

            <div className="nav-section-label">More</div>
            <button
              type="button"
              onClick={() => setMoreOpen((v) => !v)}
              className="nav-item w-full"
              aria-expanded={moreOpen}
            >
              <span className="nav-tile"><ChevronRight size={14} className="text-white/60" /></span>
              <span>Other screens</span>
              <span className="ml-auto text-[11px] text-white/40 num">{moreItems.length}</span>
            </button>
            {moreOpen ? moreItems.map((item) => (
              <NavItem key={item.path} item={item} onNavigate={close} />
            )) : null}

            {role === 'lecturer' ? (
              <NavItem
                item={{ path: '/contribution/tracking', icon: BarChart3, label: 'Contribution tracking', area: 'projects' }}
                onNavigate={close}
              />
            ) : null}
          </nav>

          <div className="mt-auto px-[11px] pb-3 pt-2.5 border-t border-white/[.06]">
            <button
              type="button"
              onClick={() => { close(); onLogout(); }}
              className="nav-item w-full"
              style={{ color: 'rgba(233,144,138,.78)' }}
            >
              <span className="nav-tile"><LogOut size={14} className="text-white/60" /></span>
              <span>Sign out</span>
            </button>
          </div>
        </div>
      </aside>
    </>
  );
};

const NavItem = ({ item, onNavigate, badge = 0 }) => (
  <NavLink
    to={item.path}
    onClick={onNavigate}
    className={({ isActive }) => `nav-item${isActive ? ' active' : ''}`}
  >
    <span className="nav-tile">
      <item.icon size={14} style={{ color: AREA_ICON[item.area] || '#A7B2C4' }} />
    </span>
    <span>{item.label}</span>
    {badge > 0 ? (
      <span className="ml-auto grid h-[18px] min-w-[18px] place-items-center rounded-full bg-danger px-[5px] text-[10px] font-semibold text-white">
        {badge > 99 ? '99+' : badge}
      </span>
    ) : null}
  </NavLink>
);

const AREA_ICON = {
  cls: '#8FB4E8',
  att: '#6FC4A0',
  prj: '#E0B368',
  ann: '#DB94B0',
  hub: '#A7B2C4',
};

export default Sidebar;
