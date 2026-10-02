import React, { useState } from 'react';
import { NavLink, useNavigate } from 'react-router-dom';
import { 
  LayoutDashboard, 
  Users, 
  FolderKanban, 
  ClipboardCheck, 
  BarChart3, 
  Bell, 
  Settings, 
  LogOut, 
  CheckSquare,
  UserCircle,
  BookOpen,
  Calendar,
  Menu,
  X,
  Shield,
  ChevronLeft
} from 'lucide-react';

const Sidebar = ({ onLogout, userName = 'User', userRole = 'student' }) => {
  const [isMobileOpen, setIsMobileOpen] = useState(false);
  const [isCollapsed, setIsCollapsed] = useState(false);
  const navigate = useNavigate();
  const initials = userName.split(' ').map(n => n[0]).join('').toUpperCase().slice(0, 2);

  const getNavItems = () => {
    const commonItems = [
      { path: '/dashboard', icon: LayoutDashboard, label: 'Dashboard' },
      { path: '/profile', icon: UserCircle, label: 'Profile' },
    ];

    const studentItems = [
      { type: 'label', text: 'Academics' },
      { path: '/courses', icon: BookOpen, label: 'Courses' },
      { path: '/attendance', icon: Calendar, label: 'Attendance' },
      { path: '/projects', icon: FolderKanban, label: 'Projects' },
      { path: '/tasks', icon: CheckSquare, label: 'Tasks' },
      { path: '/groups', icon: Users, label: 'Groups' },
      { type: 'label', text: 'Evaluation' },
      { path: '/assessment', icon: ClipboardCheck, label: 'Assessment' },
      { path: '/contribution', icon: BarChart3, label: 'Contributions' },
      { type: 'label', text: 'Info' },
      { path: '/announcements', icon: Bell, label: 'Announcements' },
      { path: '/academic', icon: Calendar, label: 'Academic Calendar' },
    ];

    const lecturerItems = [
      { type: 'label', text: 'Academics' },
      { path: '/courses', icon: BookOpen, label: 'My Courses' },
      { path: '/attendance', icon: Calendar, label: 'Attendance' },
      { path: '/projects', icon: FolderKanban, label: 'Projects' },
      { path: '/tasks', icon: CheckSquare, label: 'Tasks' },
      { path: '/groups', icon: Users, label: 'Groups' },
      { type: 'label', text: 'Evaluation' },
      { path: '/assessment', icon: ClipboardCheck, label: 'Assessment' },
      { path: '/contribution', icon: BarChart3, label: 'Contributions' },
      { path: '/contribution/tracking', icon: BarChart3, label: 'Contribution Tracking' },
      { type: 'label', text: 'Info' },
      { path: '/announcements', icon: Bell, label: 'Announcements' },
      { path: '/academic', icon: Calendar, label: 'Academic Calendar' },
    ];

    const adminItems = [
      { type: 'label', text: 'Administration' },
      { path: '/admin/dashboard', icon: Shield, label: 'Admin Dashboard' },
      { path: '/admin/users', icon: Users, label: 'User Management' },
      { type: 'label', text: 'Academics' },
      { path: '/courses', icon: BookOpen, label: 'Course Catalogue' },
      { path: '/attendance', icon: Calendar, label: 'Attendance' },
      { path: '/academic', icon: Calendar, label: 'Academic Calendar' },
    ];

    if (userRole === 'admin') {
      return [...commonItems, ...adminItems];
    } else if (userRole === 'lecturer') {
      return [...commonItems, ...lecturerItems];
    } else {
      return [...commonItems, ...studentItems];
    }
  };

  const navItems = getNavItems();

  const toggleSidebar = () => setIsMobileOpen(!isMobileOpen);
  const closeSidebar = () => setIsMobileOpen(false);

  const roleColor = userRole === 'admin' ? '#DC2626' : userRole === 'lecturer' ? '#3F35B5' : '#2563EB';
  const roleBg = userRole === 'admin' ? 'rgba(220,38,38,0.15)' : userRole === 'lecturer' ? 'rgba(63,53,181,0.15)' : 'rgba(37,99,235,0.15)';

  const SidebarContent = () => (
    <div className="flex flex-col h-full">
      {/* Logo */}
      <div className="px-5 pt-5 pb-4">
        <div className="flex items-center gap-3">
          <div className="w-10 h-10 rounded-xl flex items-center justify-center" style={{ backgroundColor: '#3F35B5' }}>
            <span className="text-white font-bold text-base tracking-tight">FET</span>
          </div>
          <div>
            <h1 className="text-[15px] font-bold text-white leading-tight">FET Platform</h1>
            <p className="text-[11px] text-white/35 font-medium">Engineering Management</p>
          </div>
        </div>
      </div>

      {/* Divider */}
      <div className="mx-4 h-px bg-white/8"></div>

      {/* User Info */}
      <div className="px-4 py-4">
        <div className="flex items-center gap-3 px-2 py-2.5 rounded-xl" style={{ backgroundColor: 'rgba(255,255,255,0.06)' }}>
          <div className="w-9 h-9 rounded-lg flex items-center justify-center font-bold text-white text-sm" style={{ backgroundColor: roleColor }}>
            {initials || 'U'}
          </div>
          <div className="flex-1 min-w-0">
            <p className="text-[13px] font-semibold text-white truncate">{userName}</p>
            <div className="flex items-center gap-1.5 mt-0.5">
              <span className="w-1.5 h-1.5 rounded-full" style={{ backgroundColor: roleColor }}></span>
              <p className="text-[11px] capitalize font-medium" style={{ color: 'rgba(255,255,255,0.45)' }}>{userRole}</p>
            </div>
          </div>
        </div>
      </div>

      {/* Navigation */}
      <nav className="flex-1 px-3 overflow-y-auto" style={{ scrollbarWidth: 'thin' }}>
        {navItems.map((item, index) => {
          if (item.type === 'label') {
            return (
              <div key={`label-${index}`} className="nav-section-label">
                {item.text}
              </div>
            );
          }
          return (
            <NavLink
              key={item.path}
              to={item.path}
              onClick={closeSidebar}
              className={({ isActive }) =>
                `nav-item ${isActive ? 'active' : ''}`
              }
            >
              <item.icon size={18} strokeWidth={2} />
              <span>{item.label}</span>
            </NavLink>
          );
        })}
      </nav>

      {/* Bottom Actions */}
      <div className="px-3 pb-4 mt-auto">
        <div className="h-px bg-white/8 mb-3 mx-1"></div>
        <button 
          onClick={() => { closeSidebar(); navigate('/profile'); }}
          className="nav-item w-full"
        >
          <Settings size={18} strokeWidth={2} />
          <span>Settings</span>
        </button>
        <button 
          onClick={() => { onLogout(); closeSidebar(); }}
          className="nav-item w-full"
          style={{ color: 'rgba(252,165,165,0.7)' }}
        >
          <LogOut size={18} strokeWidth={2} />
          <span>Logout</span>
        </button>
      </div>
    </div>
  );

  return (
    <>
      {/* Mobile Hamburger */}
      <button
        onClick={toggleSidebar}
        className="lg:hidden fixed top-3 left-3 z-[60] p-2 bg-[#0F0B3D] text-white rounded-lg shadow-lg"
        aria-label="Toggle navigation"
      >
        {isMobileOpen ? <X size={22} /> : <Menu size={22} />}
      </button>

      {/* Mobile Overlay */}
      {isMobileOpen && (
        <div 
          className="lg:hidden fixed inset-0 bg-black/50 z-40 backdrop-blur-sm"
          onClick={closeSidebar}
        />
      )}

      {/* Sidebar */}
      <aside className={`
        sidebar text-white flex flex-col fixed lg:relative z-50
        transition-transform duration-200 ease-out
        ${isMobileOpen ? 'translate-x-0' : '-translate-x-full lg:translate-x-0'}
        h-full
        ${isCollapsed ? 'w-[72px]' : 'w-64'}
      `}>
        <SidebarContent />
      </aside>
    </>
  );
};

export default Sidebar;
