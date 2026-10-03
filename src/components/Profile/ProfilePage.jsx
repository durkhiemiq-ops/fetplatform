import React, { useState, useEffect } from 'react';
import { Link } from 'react-router-dom';
import { Edit2, Save, X, Mail, Building, ArrowRight, AlertCircle } from 'lucide-react';
import { profileApi, normalizeRole } from '../../lib/profile';
import { projectsApi } from '../../lib/projects';
import { statusBadge } from '../Projects/projectUi';

const getInitials = (name) => name.split(/\s+/).filter(Boolean).map((part) => part[0]).join('').toUpperCase().slice(0, 2) || 'U';
const roleLabel = (role) => ({ student: 'Student', lecturer: 'Lecturer', admin: 'Administrator' }[role] || 'User');
const errorMessage = (error, fallback) => error.response?.data?.error?.message || fallback;

const ProfilePage = () => {
  const [me, setMe] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [isEditing, setIsEditing] = useState(false);
  const [saving, setSaving] = useState(false);
  const [success, setSuccess] = useState('');
  const [form, setForm] = useState({ first_name: '', last_name: '' });
  const [departmentName, setDepartmentName] = useState('');
  const [projects, setProjects] = useState([]);
  const [projectsLoading, setProjectsLoading] = useState(false);
  const [projectsError, setProjectsError] = useState('');

  const role = normalizeRole(me?.role || '');
  const departmentId = me?.department;
  const userId = me?.id;

  useEffect(() => {
    let active = true;
    profileApi.me()
      .then((data) => { if (active) setMe(data); })
      .catch((err) => { if (active) setError(errorMessage(err, 'Could not load your profile.')); })
      .finally(() => { if (active) setLoading(false); });
    return () => { active = false; };
  }, []);

  // Reference data and projects are independent of the identity request.
  useEffect(() => {
    let active = true;
    setDepartmentName('');
    if (departmentId) {
      profileApi.departments()
        .then((departments) => {
          if (active) setDepartmentName(departments.find((department) => department.id === departmentId)?.name || 'Unavailable');
        })
        .catch(() => { if (active) setDepartmentName('Unavailable'); });
    }
    return () => { active = false; };
  }, [departmentId]);

  useEffect(() => {
    let active = true;
    if (role !== 'lecturer' || !userId) return () => { active = false; };
    setProjectsLoading(true);
    setProjectsError('');
    projectsApi.listProjects()
      .then((data) => {
        if (active) setProjects(data.filter((project) => [project.owner, project.supervisor, project.created_by].includes(userId)));
      })
      .catch((err) => { if (active) setProjectsError(errorMessage(err, 'Could not load your projects.')); })
      .finally(() => { if (active) setProjectsLoading(false); });
    return () => { active = false; };
  }, [role, userId]);

  const startEdit = () => {
    setForm({ first_name: me.first_name || '', last_name: me.last_name || '' });
    setError('');
    setSuccess('');
    setIsEditing(true);
  };

  const handleSave = async (event) => {
    event.preventDefault();
    setSaving(true);
    setError('');
    setSuccess('');
    try {
      const updated = await profileApi.updateMe({
        first_name: form.first_name.trim(),
        last_name: form.last_name.trim(),
      });
      setMe(updated);
      setIsEditing(false);
      setSuccess('Name updated successfully.');
      window.dispatchEvent(new CustomEvent('fet-profile-updated'));
    } catch (err) {
      setError(errorMessage(err, 'Could not save your profile.'));
    } finally {
      setSaving(false);
    }
  };

  if (loading) {
    return <div className="text-center py-16 text-text-secondary text-[13px]">Loading profile...</div>;
  }
  if (!me) {
    return (
      <div className="text-center py-12" role="alert">
        <AlertCircle size={40} className="mx-auto text-danger mb-3" />
        <h2 className="text-[20px] font-bold text-text-primary">Profile unavailable</h2>
        <p className="text-[13px] text-text-secondary mt-1">{error || 'Please log in again.'}</p>
      </div>
    );
  }

  const fullName = [me.first_name, me.last_name].filter(Boolean).join(' ') || me.email;
  const department = departmentId ? departmentName || 'Loading...' : 'Not assigned';

  return (
    <div className="space-y-4 md:space-y-6 max-w-4xl mx-auto">
      <div className="flex flex-col sm:flex-row items-start sm:items-center justify-between gap-3">
        <div>
          <h2 className="text-xl font-bold text-text-primary">My Profile</h2>
          <p className="text-sm text-text-secondary">View your account details and update your name.</p>
        </div>
        <button
          type="button"
          onClick={() => (isEditing ? setIsEditing(false) : startEdit())}
          disabled={saving}
          className={isEditing ? 'fet-btn-danger' : 'fet-btn-primary'}
        >
          {isEditing ? <X size={18} /> : <Edit2 size={18} />}
          {isEditing ? 'Cancel' : 'Edit Name'}
        </button>
      </div>

      {success && <div role="status" className="bg-green-50 border border-green-200 text-green-700 px-4 py-3 rounded-xl text-sm">{success}</div>}
      {error && (
        <div role="alert" className="flex items-center gap-2 bg-red-50 border border-red-200 text-red-700 px-4 py-3 rounded-xl text-[13px]">
          <AlertCircle size={16} /> {error}
        </div>
      )}

      <div className="fet-card overflow-hidden">
        <div className="fet-welcome-banner">
          <div className="flex flex-col sm:flex-row items-center sm:items-start gap-4">
            <div className="w-16 h-16 md:w-20 md:h-20 rounded-full bg-primary flex items-center justify-center text-xl md:text-2xl font-bold flex-shrink-0">
              {getInitials(fullName)}
            </div>
            <div className="text-center sm:text-left flex-1">
              <h3 className="text-lg md:text-xl font-bold">{fullName}</h3>
              <p className="text-[#8683BA] text-sm">{roleLabel(role)}</p>
            </div>
          </div>
        </div>

        <form onSubmit={handleSave} className="p-4 md:p-6">
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
            <Field label="First Name">
              {isEditing ? (
                <input aria-label="First name" autoComplete="given-name" required maxLength={150} disabled={saving} value={form.first_name} onChange={(event) => setForm({ ...form, first_name: event.target.value })} className="fet-input" />
              ) : <p>{me.first_name || 'Not set'}</p>}
            </Field>
            <Field label="Last Name">
              {isEditing ? (
                <input aria-label="Last name" autoComplete="family-name" required maxLength={150} disabled={saving} value={form.last_name} onChange={(event) => setForm({ ...form, last_name: event.target.value })} className="fet-input" />
              ) : <p>{me.last_name || 'Not set'}</p>}
            </Field>
            <Field label={role === 'student' ? 'Matricule Number' : 'Staff ID'}>
              <p>{(role === 'student' ? me.matricule : me.staffid) || 'Not assigned'}</p>
            </Field>
            <Field label="Email">
              <p className="flex items-center gap-1.5"><Mail size={14} className="text-text-secondary" />{me.email}</p>
            </Field>
            <Field label="Department">
              <p className="flex items-center gap-1.5"><Building size={14} className="text-text-secondary" />{department}</p>
            </Field>
            <Field label="Role"><p>{roleLabel(role)}</p></Field>
          </div>
          {isEditing && (
            <div className="mt-6 pt-6 border-t border-border-default flex justify-end">
              <button type="submit" disabled={saving} className="fet-btn-primary">
                <Save size={18} />{saving ? 'Saving...' : 'Save Changes'}
              </button>
            </div>
          )}
        </form>
      </div>

      {role === 'lecturer' && (
        <div className="fet-card p-4 md:p-6">
          <div className="flex items-center justify-between mb-3">
            <h4 className="text-[15px] font-bold text-text-primary">Projects I Manage</h4>
            <Link to="/projects" className="text-primary text-[13px] flex items-center gap-1">Manage <ArrowRight size={14} /></Link>
          </div>
          {projectsLoading ? <p className="text-text-secondary text-[13px]">Loading projects...</p> : projectsError ? (
            <p role="alert" className="text-danger text-[13px]">{projectsError}</p>
          ) : projects.length === 0 ? (
            <p className="text-text-secondary text-[13px] text-center py-4">No projects yet.</p>
          ) : (
            <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
              {projects.map((project) => (
                <Link key={project.id} to={`/projects/${project.id}`} className="flex items-center justify-between gap-3 p-3 bg-page-bg rounded-lg">
                  <p className="text-[13px] font-medium text-text-primary truncate">{project.title}</p>
                  {statusBadge(project.status)}
                </Link>
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
    <p className="block text-xs font-semibold text-text-secondary uppercase tracking-wider">{label}</p>
    <div className="mt-1 text-text-primary font-medium text-[13px]">{children}</div>
  </div>
);

export default ProfilePage;
