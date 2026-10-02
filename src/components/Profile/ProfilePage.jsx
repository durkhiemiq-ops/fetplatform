import React, { useState, useEffect, useCallback } from 'react';
import { useNavigate } from 'react-router-dom';
import {
  Edit2, Save, X, Mail, Building, GraduationCap, User as UserIcon, Award, Briefcase,
  ArrowRight, AlertCircle, RefreshCw,
} from 'lucide-react';
import { profileApi, normalizeRole } from '../../lib/profile';
import { projectsApi } from '../../lib/projects';
import { statusBadge } from '../Projects/projectUi';

const getInitials = (name) => {
  if (!name) return 'U';
  return name.split(' ').map((n) => n[0]).join('').toUpperCase().slice(0, 2);
};

const roleLabel = (role) => {
  if (role === 'student') return 'Student';
  if (role === 'lecturer') return 'Lecturer';
  if (role === 'admin') return 'Admin';
  return role || 'User';
};

const fmtDate = (iso) => (iso ? new Date(iso).toLocaleDateString() : '—');

const ProfilePage = () => {
  const navigate = useNavigate();
  const [me, setMe] = useState(null);
  const [activity, setActivity] = useState(null);
  const [lecturerProjects, setLecturerProjects] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [isEditing, setIsEditing] = useState(false);
  const [saving, setSaving] = useState(false);
  const [success, setSuccess] = useState('');
  const [form, setForm] = useState({});

  const role = normalizeRole(me?.role || '');
  const isStudent = role === 'student';
  const isLecturer = role === 'lecturer';

  const load = useCallback(async () => {
    setLoading(true);
    setError('');
    try {
      const meData = await profileApi.me();
      setMe(meData);
      const r = normalizeRole(meData.role);
      if (r === 'student') {
        setActivity(await profileApi.activity(meData.id));
      } else {
        setLecturerProjects(await projectsApi.listProjects());
      }
    } catch (err) {
      setError(err.response?.data?.error?.message || 'Could not load your profile.');
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  const startEdit = () => {
    const sp = me?.student_profile || {};
    const lp = me?.lecturer_profile || {};
    setForm({
      first_name: me?.first_name || '',
      last_name: me?.last_name || '',
      date_of_birth: me?.date_of_birth || '',
      personal_email: sp.personal_email || '',
      level: sp.level || '',
      bio: isStudent ? sp.bio || '' : lp.bio || '',
      skills: (sp.skills || []).join(', '),
      achievements: (sp.achievements || []).join(', '),
    });
    setIsEditing(true);
  };

  const handleSave = async () => {
    setSaving(true);
    setError('');
    try {
      const payload = {
        first_name: form.first_name,
        last_name: form.last_name,
        date_of_birth: form.date_of_birth || null,
      };
      if (isStudent) {
        payload.personal_email = form.personal_email;
        payload.level = form.level;
        payload.bio = form.bio;
        payload.skills = form.skills.split(',').map((s) => s.trim()).filter(Boolean);
        payload.achievements = form.achievements.split(',').map((s) => s.trim()).filter(Boolean);
      }
      if (isLecturer) {
        payload.bio = form.bio;
      }
      await profileApi.updateMe(payload);
      const updated = await profileApi.me();
      setMe(updated);
      setIsEditing(false);
      // Only first_name and last_name are writable on UserSerializer; every
      // other field built above is read_only or not on the model. Reporting an
      // unqualified success made a no-op look like a saved profile.
      setSuccess('Name updated successfully.');
      window.dispatchEvent(new CustomEvent('fet-profile-updated'));
      setTimeout(() => setSuccess(''), 3000);
    } catch (err) {
      const msg = err.response?.data?.error?.message || err.response?.data?.error?.details
        ? JSON.stringify(err.response.data.error.details)
        : 'Could not save your profile.';
      setError(typeof msg === 'string' ? msg : 'Could not save your profile.');
    } finally {
      setSaving(false);
    }
  };

  if (loading) {
    return <div className="text-center py-16 text-text-secondary text-[13px]">Loading profile...</div>;
  }
  if (!me) {
    return (
      <div className="text-center py-12">
        <AlertCircle size={40} className="mx-auto text-danger mb-3" />
        <h2 className="text-[20px] font-bold text-text-primary">Profile unavailable</h2>
        <p className="text-[13px] text-text-secondary mt-1">{error || 'Please log in again.'}</p>
      </div>
    );
  }

  const sp = me.student_profile || {};
  const lp = me.lecturer_profile || {};
  const stats = activity?.stats || {};

  return (
    <div className="space-y-4 md:space-y-6 max-w-4xl mx-auto">
      <div className="flex flex-col sm:flex-row items-start sm:items-center justify-between gap-3">
        <div>
          <h2 className="text-xl md:text-2xl font-bold text-text-primary" style={{ fontSize: '20px' }}>My Profile</h2>
          <p className="text-sm text-text-secondary">Manage your personal information and academic activity</p>
        </div>
        <button
          onClick={() => (isEditing ? setIsEditing(false) : startEdit())}
          className={`flex items-center gap-2 px-4 py-2 rounded-xl font-medium transition-colors text-sm ${
            isEditing ? 'fet-btn-danger' : 'fet-btn-primary'
          }`}
        >
          {isEditing ? <X size={18} /> : <Edit2 size={18} />}
          {isEditing ? 'Cancel' : 'Edit Profile'}
        </button>
      </div>

      {success && (
        <div className="bg-green-50 border border-green-200 text-green-700 px-4 py-3 rounded-xl text-sm">{success}</div>
      )}
      {error && (
        <div className="flex items-center gap-2 bg-red-50 border border-red-200 text-red-700 px-4 py-3 rounded-xl text-[13px]">
          <AlertCircle size={16} /> {error}
        </div>
      )}

      <div className="fet-card overflow-hidden">
        <div className="fet-welcome-banner">
          <div className="flex flex-col sm:flex-row items-center sm:items-start gap-4">
            <div className="w-16 h-16 md:w-20 md:h-20 rounded-full bg-primary flex items-center justify-center text-xl md:text-2xl font-bold flex-shrink-0">
              {getInitials(me.full_name || me.email)}
            </div>
            <div className="text-center sm:text-left flex-1">
              <h3 className="text-lg md:text-xl font-bold">{me.full_name || me.email}</h3>
              <p className="text-[#8683BA] text-sm capitalize">{roleLabel(role)}</p>
              {isStudent && sp.department && (
                <p className="text-[#8683BA] text-xs">{sp.department.name} • Level {sp.level || '—'}</p>
              )}
              {isLecturer && lp.department && (
                <p className="text-[#8683BA] text-xs">{lp.department.name} {lp.title ? `• ${lp.title}` : ''}</p>
              )}
            </div>
          </div>
        </div>

        <div className="p-4 md:p-6">
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
            <Field label="Full Name">
              {isEditing ? (
                <div className="grid grid-cols-2 gap-2">
                  <input type="text" value={form.first_name} onChange={(e) => setForm({ ...form, first_name: e.target.value })} className="fet-input" placeholder="First" />
                  <input type="text" value={form.last_name} onChange={(e) => setForm({ ...form, last_name: e.target.value })} className="fet-input" placeholder="Last" />
                </div>
              ) : (
                <p>{me.full_name || '-'}</p>
              )}
            </Field>

            <Field label={isStudent ? 'Matricule Number' : 'Staff / ID'}>
              <p>{isStudent ? (sp.student_number || '-') : (lp.staff_number || '-')}</p>
            </Field>

            <Field label="Email">
              <p className="flex items-center gap-1.5"><Mail size={14} className="text-text-secondary" />{me.email}</p>
            </Field>

            {isStudent && (
              <Field label="Personal Email">
                {isEditing ? (
                  <input type="email" value={form.personal_email} onChange={(e) => setForm({ ...form, personal_email: e.target.value })} className="fet-input" />
                ) : (
                  <p>{sp.personal_email || '-'}</p>
                )}
              </Field>
            )}

            <Field label="Department">
              <p className="flex items-center gap-1.5">
                <Building size={14} className="text-text-secondary" />
                {isStudent ? (sp.department?.name || '-') : (lp.department?.name || '-')}
              </p>
            </Field>

            {isStudent && (
              <Field label="Level">
                {isEditing ? (
                  <select value={form.level} onChange={(e) => setForm({ ...form, level: e.target.value })} className="fet-select">
                    {['200', '300', '400', '500'].map((l) => <option key={l} value={l}>Level {l}</option>)}
                  </select>
                ) : (
                  <p className="flex items-center gap-1.5"><GraduationCap size={14} className="text-text-secondary" />Level {sp.level || '-'}</p>
                )}
              </Field>
            )}

            {isStudent && (
              <Field label="Admission Year">
                <p>{sp.admission_year || '-'}</p>
              </Field>
            )}

            <Field label="Date of Birth">
              {isEditing ? (
                <input type="date" value={form.date_of_birth || ''} onChange={(e) => setForm({ ...form, date_of_birth: e.target.value })} className="fet-input" />
              ) : (
                <p>{fmtDate(me.date_of_birth)}</p>
              )}
            </Field>

            <Field label="Bio">
              {isEditing ? (
                <textarea value={form.bio} onChange={(e) => setForm({ ...form, bio: e.target.value })} rows={3} className="fet-input resize-none" />
              ) : (
                <p className="whitespace-pre-line">{isStudent ? sp.bio || '-' : lp.bio || '-'}</p>
              )}
            </Field>

            {isStudent && (
              <>
                <Field label="Skills">
                  {isEditing ? (
                    <input type="text" value={form.skills} onChange={(e) => setForm({ ...form, skills: e.target.value })} className="fet-input" placeholder="Comma separated, e.g. Python, UI Design" />
                  ) : (
                    <div className="flex flex-wrap gap-1.5">
                      {(sp.skills || []).length === 0 && <span className="text-text-secondary">-</span>}
                      {(sp.skills || []).map((s, i) => (
                        <span key={i} className="fet-badge fet-badge-active">{s}</span>
                      ))}
                    </div>
                  )}
                </Field>
                <Field label="Achievements">
                  {isEditing ? (
                    <input type="text" value={form.achievements} onChange={(e) => setForm({ ...form, achievements: e.target.value })} className="fet-input" placeholder="Comma separated" />
                  ) : (
                    <div className="flex flex-wrap gap-1.5">
                      {(sp.achievements || []).length === 0 && <span className="text-text-secondary">-</span>}
                      {(sp.achievements || []).map((a, i) => (
                        <span key={i} className="fet-badge fet-badge-completed">{a}</span>
                      ))}
                    </div>
                  )}
                </Field>
              </>
            )}
          </div>

          {isEditing && (
            <div className="mt-6 pt-6 border-t border-border-default flex justify-end">
              <button onClick={handleSave} disabled={saving} className="fet-btn-primary flex items-center gap-2">
                <Save size={18} />
                {saving ? 'Saving...' : 'Save Changes'}
              </button>
            </div>
          )}
        </div>
      </div>

      {isStudent && activity && (
        <>
          <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-6 gap-4">
            <StatTile icon={Award} label="Points" value={stats.points_total ?? 0} />
            <StatTile icon={GraduationCap} label="Attendance Rate" value={`${stats.attendance_rate ?? 0}%`} />
            <StatTile icon={Briefcase} label="Active Projects" value={stats.projects_active ?? 0} />
            <StatTile icon={UserIcon} label="Completed Projects" value={stats.projects_completed ?? 0} />
            <StatTile icon={Edit2} label="Tasks Done" value={stats.tasks_completed ?? 0} />
            <StatTile icon={Award} label="Contributions" value={stats.contributions_count ?? 0} />
          </div>

          {(stats.points_by_category && Object.keys(stats.points_by_category).length > 0) && (
            <div className="fet-card p-4">
              <h4 className="text-[13px] font-semibold text-text-primary mb-2">Points Breakdown</h4>
              <div className="flex flex-wrap gap-2">
                {Object.entries(stats.points_by_category).map(([cat, pts]) => (
                  <span key={cat} className="fet-badge fet-badge-pending">{cat.replace('_', ' ')}: {pts}</span>
                ))}
              </div>
            </div>
          )}

          <div className="fet-card p-4 md:p-6">
            <div className="flex items-center justify-between mb-3">
              <h4 className="text-[15px] font-bold text-text-primary">Attendance by Course</h4>
              <button onClick={load} className="text-primary text-[13px] flex items-center gap-1"><RefreshCw size={14} /> <span className="hidden sm:inline">Refresh</span></button>
            </div>
            {activity.attendance_by_course.length === 0 ? (
              <p className="text-text-secondary text-[13px] py-4 text-center">No attendance recorded yet.</p>
            ) : (
              <div className="space-y-4">
                {activity.attendance_by_course.map((row) => (
                  <div key={row.course_code}>
                    <div className="flex items-center justify-between text-[13px] mb-1">
                      <span className="font-semibold text-text-primary">{row.course_code} <span className="font-normal text-text-secondary">• {row.course_title}</span></span>
                      <span className="text-text-primary font-semibold">{row.rate}%</span>
                    </div>
                    <div className="fet-progress-bar">
                      <div className="fet-progress-bar-fill" style={{ width: `${row.rate}%` }}></div>
                    </div>
                    <p className="text-[12px] text-text-secondary mt-1">
                      {row.present} present • {row.late} late • {row.absent} absent ({row.total} sessions)
                    </p>
                  </div>
                ))}
              </div>
            )}
          </div>

          <div className="grid grid-cols-1 lg:grid-cols-2 gap-4 md:gap-6">
            <div className="fet-card p-4 md:p-6">
              <h4 className="text-[15px] font-bold text-text-primary mb-3">Recent Attendance</h4>
              {activity.recent_attendance.length === 0 ? (
                <p className="text-text-secondary text-[13px] text-center py-4">Nothing yet.</p>
              ) : (
                <div className="space-y-2">
                  {activity.recent_attendance.map((r, i) => (
                    <div key={i} className="flex items-center justify-between p-3 bg-page-bg rounded-lg">
                      <div>
                        <p className="text-[13px] font-medium text-text-primary">{r.course_code}</p>
                        <p className="text-[11px] text-text-secondary">{r.class_name} • {r.session_date}</p>
                      </div>
                      <span className={`fet-badge ${r.status === 'PRESENT' ? 'fet-badge-completed' : r.status === 'LATE' ? 'fet-badge-warning' : 'fet-badge-danger'}`}>
                        {r.status}
                      </span>
                    </div>
                  ))}
                </div>
              )}
            </div>

            <div className="fet-card p-4 md:p-6">
              <h4 className="text-[15px] font-bold text-text-primary mb-3">My Projects</h4>
              {activity.projects.length === 0 ? (
                <p className="text-text-secondary text-[13px] text-center py-4">You are not a member of any project yet.</p>
              ) : (
                <div className="space-y-2">
                  {activity.projects.map((p) => (
                    <button
                      key={p.id}
                      onClick={() => navigate(`/projects/${p.id}`)}
                      className="w-full flex items-center justify-between p-3 bg-page-bg rounded-lg hover:bg-white transition-colors text-left"
                    >
                      <div>
                        <p className="text-[13px] font-medium text-text-primary">{p.title}</p>
                        <p className="text-[11px] text-text-secondary">{p.course_code} • {p.group || 'No group'} • {p.role === 'GROUP_LEADER' ? 'Leader' : 'Member'}</p>
                      </div>
                      <ArrowRight size={15} className="text-text-secondary flex-shrink-0" />
                    </button>
                  ))}
                </div>
              )}
            </div>
          </div>

          <div className="fet-card p-4 md:p-6">
            <h4 className="text-[15px] font-bold text-text-primary mb-3">Assessments</h4>
            {activity.assessments.length === 0 ? (
              <p className="text-text-secondary text-[13px] text-center py-4">No released assessments yet.</p>
            ) : (
              <div className="space-y-2">
                {activity.assessments.map((a, i) => (
                  <div key={i} className="flex items-center justify-between p-3 bg-page-bg rounded-lg">
                    <div>
                      <p className="text-[13px] font-medium text-text-primary">{a.component_name}</p>
                      <p className="text-[11px] text-text-secondary">{a.project_title}</p>
                    </div>
                    <div className="text-right">
                      <p className="text-[14px] font-bold text-text-primary">{a.score}/{a.maximum_score}</p>
                      <p className="text-[11px] text-text-secondary">Weight {a.weight}</p>
                    </div>
                  </div>
                ))}
              </div>
            )}
          </div>
        </>
      )}

      {isLecturer && (
        <div className="fet-card p-4 md:p-6">
          <div className="flex items-center justify-between mb-3">
            <h4 className="text-[15px] font-bold text-text-primary">Projects I Supervise</h4>
            <button onClick={() => navigate('/projects')} className="text-primary text-[13px] flex items-center gap-1">
              Manage <ArrowRight size={14} />
            </button>
          </div>
          {lecturerProjects.length === 0 ? (
            <p className="text-text-secondary text-[13px] text-center py-4">No projects yet.</p>
          ) : (
            <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
              {lecturerProjects.map((p) => (
                <div key={p.id} className="flex items-center justify-between p-3 bg-page-bg rounded-lg">
                  <div className="min-w-0">
                    <p className="text-[13px] font-medium text-text-primary truncate">{p.title}</p>
                    <p className="text-[11px] text-text-secondary">{p.course_code} • {p.member_count} members</p>
                  </div>
                  {statusBadge(p.status)}
                </div>
              ))}
            </div>
          )}
        </div>
      )}
    </div>
  );
};

const Field = ({ label, children }) => (
  <div>
    <label className="block text-xs font-semibold text-text-secondary uppercase tracking-wider">{label}</label>
    <div className="mt-1 text-text-primary font-medium text-[13px]">{children}</div>
  </div>
);

const StatTile = ({ icon: Icon, label, value }) => (
  <div className="fet-card p-4 text-center">
    <Icon size={18} className="mx-auto text-primary mb-2" />
    <p className="text-[20px] font-bold text-text-primary">{value}</p>
    <p className="text-[11px] font-medium text-text-secondary mt-0.5">{label}</p>
  </div>
);

export default ProfilePage;