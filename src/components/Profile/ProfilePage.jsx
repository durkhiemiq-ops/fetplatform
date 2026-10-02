import React, { useState } from 'react';
import { Edit2, Save, X, User, Mail, Building, GraduationCap, Phone, MapPin } from 'lucide-react';
import { updateProfile } from '../../api/auth';

const ProfilePage = ({ user }) => {
  const [isEditing, setIsEditing] = useState(false);
  const [formData, setFormData] = useState({
    fullName: user?.fullName || '',
    email: user?.email || '',
    department: user?.department || '',
    level: user?.level || '',
    matricule: user?.matricule || '',
    phone: user?.phone || '',
    address: user?.address || '',
  });
  const [success, setSuccess] = useState('');
  const [error, setError] = useState('');
  const [isSaving, setIsSaving] = useState(false);

  const handleChange = (e) => {
    const { name, value } = e.target;
    setFormData(prev => ({ ...prev, [name]: value }));
  };

  const handleSave = async () => {
    setIsSaving(true);
    setError('');
    setSuccess('');
    // Backend UserSerializer only accepts first_name/last_name via PATCH
    // /accounts/me/ — email and role are read-only server-side.
    const nameParts = (formData.fullName || '').trim().split(/\s+/);
    try {
      const updated = await updateProfile({
        first_name: nameParts[0] || '',
        last_name: nameParts.slice(1).join(' ') || nameParts[0] || '',
      });
      const mapped = { ...user, ...updated, fullName: `${updated.first_name} ${updated.last_name}`.trim() };
      window.dispatchEvent(new CustomEvent('fet-profile-updated'));
      setSuccess('✅ Profile updated successfully!');
      setIsEditing(false);
      setTimeout(() => setSuccess(''), 3000);
    } catch (err) {
      setError(err.message || 'Could not save your profile.');
    } finally {
      setIsSaving(false);
    }
  };

  const getInitials = (name) => {
    if (!name) return 'U';
    return name.split(' ').map(n => n[0]).join('').toUpperCase().slice(0, 2);
  };

  const userRole = user?.role || 'student';

  return (
    <div className="space-y-4 md:space-y-6 max-w-4xl mx-auto">
      <div className="flex flex-col sm:flex-row items-start sm:items-center justify-between gap-3">
        <div>
          <h2 className="text-xl md:text-2xl font-bold text-text-primary" style={{ fontSize: '20px' }}>My Profile</h2>
          <p className="text-sm text-text-secondary">Manage your personal information</p>
        </div>
        <button
          onClick={() => setIsEditing(!isEditing)}
          className={`flex items-center gap-2 px-4 py-2 rounded-xl font-medium transition-colors text-sm ${
            isEditing 
              ? 'fet-btn-danger' 
              : 'fet-btn-primary'
          }`}
        >
          {isEditing ? <X size={18} /> : <Edit2 size={18} />}
          {isEditing ? 'Cancel' : 'Edit Profile'}
        </button>
      </div>

      {success && (
        <div className="bg-green-50 border border-green-200 text-green-700 px-4 py-3 rounded-xl text-sm">
          {success}
        </div>
      )}
      {error && (
        <div className="bg-red-50 border border-red-200 text-red-700 px-4 py-3 rounded-xl text-sm">
          {error}
        </div>
      )}

      <div className="fet-card overflow-hidden">
        {/* Header with Avatar */}
        <div className="fet-welcome-banner">
          <div className="flex flex-col sm:flex-row items-center sm:items-start gap-4">
            <div className="w-16 h-16 md:w-20 md:h-20 rounded-full bg-primary flex items-center justify-center text-xl md:text-2xl font-bold flex-shrink-0">
              {getInitials(formData.fullName || user?.fullName)}
            </div>
            <div className="text-center sm:text-left">
              <h3 className="text-lg md:text-xl font-bold">{formData.fullName || user?.fullName}</h3>
              <p className="text-[#8683BA] text-sm capitalize">
                {userRole === 'student' ? '🎓 Student' : 
                 userRole === 'lecturer' ? '👨‍🏫 Lecturer' : 
                 userRole === 'admin' ? '👑 Admin' : 'User'}
              </p>
              {userRole === 'student' && formData.level && (
                <p className="text-[#8683BA] text-xs">Level {formData.level}</p>
              )}
            </div>
          </div>
        </div>

        {/* Profile Details */}
        <div className="p-4 md:p-6">
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
            {/* Full Name */}
            <div>
              <label className="block text-xs font-semibold text-text-secondary uppercase tracking-wider">Full Name</label>
              {isEditing ? (
                <input
                  type="text"
                  name="fullName"
                  value={formData.fullName}
                  onChange={handleChange}
                  className="w-full mt-1 px-4 py-2 fet-input"
                />
              ) : (
                <p className="mt-1 text-text-primary font-medium">{formData.fullName || '-'}</p>
              )}
            </div>

            {/* Matricule */}
            <div>
              <label className="block text-xs font-semibold text-text-secondary uppercase tracking-wider">
                {userRole === 'student' ? 'Matricule Number' : 'ID'}
              </label>
              <p className="mt-1 text-text-primary font-medium">
                {userRole === 'student' ? formData.matricule || user?.matricule || '-' : user?.staffNumber || '-'}
              </p>
            </div>

            {/* Email */}
            <div>
              <label className="block text-xs font-semibold text-text-secondary uppercase tracking-wider">Email</label>
              {isEditing ? (
                <input
                  type="email"
                  name="email"
                  value={formData.email}
                  onChange={handleChange}
                  className="w-full mt-1 px-4 py-2 fet-input"
                />
              ) : (
                <p className="mt-1 text-text-primary font-medium">{formData.email || '-'}</p>
              )}
            </div>

            {/* Department */}
            <div>
              <label className="block text-xs font-semibold text-text-secondary uppercase tracking-wider">Department</label>
              {isEditing ? (
                <input
                  type="text"
                  name="department"
                  value={formData.department}
                  onChange={handleChange}
                  className="w-full mt-1 px-4 py-2 fet-input"
                />
              ) : (
                <p className="mt-1 text-text-primary font-medium">{formData.department || '-'}</p>
              )}
            </div>

            {/* Level - Only for Students */}
            {userRole === 'student' && (
              <div>
                <label className="block text-xs font-semibold text-text-secondary uppercase tracking-wider">Level</label>
                {isEditing ? (
                  <select
                    name="level"
                    value={formData.level}
                    onChange={handleChange}
                    className="w-full mt-1 px-4 py-2 fet-select"
                  >
                    <option value="100">100 Level</option>
                    <option value="200">200 Level</option>
                    <option value="300">300 Level</option>
                    <option value="400">400 Level</option>
                    <option value="500">500 Level</option>
                    <option value="MSc">MSc</option>
                    <option value="PhD">PhD</option>
                  </select>
                ) : (
                  <p className="mt-1 text-text-primary font-medium">Level {formData.level || '-'}</p>
                )}
              </div>
            )}

            {/* Phone */}
            <div>
              <label className="block text-xs font-semibold text-text-secondary uppercase tracking-wider">Phone</label>
              {isEditing ? (
                <input
                  type="text"
                  name="phone"
                  value={formData.phone}
                  onChange={handleChange}
                  placeholder="Enter phone number"
                  className="w-full mt-1 px-4 py-2 fet-input"
                />
              ) : (
                <p className="mt-1 text-text-primary font-medium">{formData.phone || 'Not set'}</p>
              )}
            </div>

            {/* Address */}
            <div className="sm:col-span-2">
              <label className="block text-xs font-semibold text-text-secondary uppercase tracking-wider">Address</label>
              {isEditing ? (
                <input
                  type="text"
                  name="address"
                  value={formData.address}
                  onChange={handleChange}
                  placeholder="Enter address"
                  className="w-full mt-1 px-4 py-2 fet-input"
                />
              ) : (
                <p className="mt-1 text-text-primary font-medium">{formData.address || 'Not set'}</p>
              )}
            </div>
          </div>

          {/* Save Button */}
          {isEditing && (
            <div className="mt-6 pt-6 border-t border-border-default flex justify-end">
              <button
                onClick={handleSave}
                disabled={isSaving}
                className="fet-btn-primary flex items-center gap-2 disabled:opacity-60"
              >
                <Save size={18} />
                {isSaving ? 'Saving…' : 'Save Changes'}
              </button>
            </div>
          )}
        </div>
      </div>
    </div>
  );
};

export default ProfilePage;
