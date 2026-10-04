import React, { useEffect, useState } from 'react';
import {
  Mail, Lock, Eye, EyeOff, User, UserPlus, ArrowLeft,
  Building, GraduationCap, BookOpen, Briefcase,
} from 'lucide-react';
import { publicApi } from '../../lib/auth';
import { academicsApi } from '../../lib/academics';

/**
 * Public self-registration.
 *
 * The visual design is preserved from the original FET sign-up screen. The
 * behaviour is not: this component calls the real backend.
 *
 * Removed relative to the original implementation, because each was a real
 * security defect rather than a style choice:
 *   - accounts were written to localStorage under `fet_users`, including the
 *     password in clear text;
 *   - "already registered" was checked against that same local array, so it
 *     detected nothing about the real database;
 *   - submitting called `onSignUp(newUser)` directly, entering the app with no
 *     server session at all;
 *   - a fake 1.5s setTimeout stood in for a network round trip;
 *   - the student/lecturer toggle set the stored role directly.
 *
 * The toggle still exists, but it now sends `account_type` — a *request*.
 * The backend resolves the real role and, for lecturers, holds the account at
 * PENDING until an administrator approves it. No field here can grant a role.
 */
const SignUp = ({ onRegistered, onSwitchToLogin }) => {
  const [showPassword, setShowPassword] = useState(false);
  const [showConfirmPassword, setShowConfirmPassword] = useState(false);
  const [departments, setDepartments] = useState([]);
  const [formData, setFormData] = useState({
    firstName: '',
    lastName: '',
    email: '',
    password: '',
    confirmPassword: '',
    accountType: 'student',
    department: '',
    level: '',
    matricule: '',
    staffid: '',
  });
  const [error, setError] = useState('');
  const [success, setSuccess] = useState('');
  const [isLoading, setIsLoading] = useState(false);

  // Departments come from the real catalogue. The original screen hardcoded
  // five invented ones with invented coordinator names.
  useEffect(() => {
    let cancelled = false;
    academicsApi
      .publicDepartments()
      .then((rows) => {
        if (!cancelled) setDepartments(Array.isArray(rows) ? rows : []);
      })
      .catch(() => {
        if (!cancelled) setDepartments([]);
      });
    return () => { cancelled = true; };
  }, []);

  const handleChange = (e) => {
    const { name, value } = e.target;
    setFormData((prev) => ({ ...prev, [name]: value }));
    setError('');
  };

  const isStudent = formData.accountType === 'student';

  const handleSubmit = async (e) => {
    e.preventDefault();
    setError('');
    setSuccess('');

    if (!formData.firstName.trim() || !formData.lastName.trim()) {
      setError('Please enter your full name.');
      return;
    }
    if (!formData.email.trim()) {
      setError('Please enter your email address.');
      return;
    }
    if (isStudent && !formData.department) {
      setError('Please select your department.');
      return;
    }
    if (isStudent && !formData.matricule.trim()) {
      setError('Matricule number is required for students.');
      return;
    }
    if (isStudent && !formData.level) {
      setError('Please select your level.');
      return;
    }
    if (!isStudent && !formData.staffid.trim()) {
      setError('Staff number is required for lecturers.');
      return;
    }
    if (!formData.password || formData.password.length < 8) {
      setError('Password must be at least 8 characters.');
      return;
    }
    if (formData.password !== formData.confirmPassword) {
      setError('Passwords do not match.');
      return;
    }

    setIsLoading(true);
    try {
      const payload = {
        account_type: isStudent ? 'student' : 'lecturer',
        email: formData.email.trim(),
        first_name: formData.firstName.trim(),
        last_name: formData.lastName.trim(),
        password: formData.password,
      };
      if (isStudent) {
        const dept = departments.find((d) => d.id === formData.department);
        payload.department = formData.department;
        payload.level = formData.level;
        payload.matricule = formData.matricule.trim().toUpperCase();
        if (dept?.code) payload.department_code = dept.code;
      } else {
        payload.staffid = formData.staffid.trim().toUpperCase();
      }

      const result = await publicApi.register(payload);
      const pendingLecturer = Boolean(result?.lecturer_approval_required);
      setSuccess(
        pendingLecturer
          ? 'Account created. Verify your email address, then an administrator will review your lecturer application.'
          : 'Account created. Verify your email address, then sign in.',
      );
      setFormData((prev) => ({ ...prev, password: '', confirmPassword: '' }));
      if (!pendingLecturer && onRegistered) {
        // Stay on the confirmation screen rather than pretending to be signed
        // in: email verification is required before a session exists.
        onRegistered(null);
      }
    } catch (err) {
      setError(readableError(err));
    } finally {
      setIsLoading(false);
    }
  };

  const inputBase = 'fet-input';
  const labelBase = 'fet-label';

  return (
    <div className="min-h-screen flex">
      {/* Left: Form */}
      <div className="flex-1 flex items-center justify-center p-6 bg-white">
        <div className="w-full max-w-[420px]">
          <button onClick={onSwitchToLogin} className="flex items-center gap-2 text-text-secondary hover:text-text-primary mb-8 transition-colors text-[13px] font-medium">
            <ArrowLeft size={16} /> Back to Login
          </button>

          <div className="mb-8">
            <div className="w-12 h-12 rounded-xl flex items-center justify-center mb-4" style={{ backgroundColor: '#3F35B5' }}>
              <UserPlus size={22} className="text-white" />
            </div>
            <h1 className="text-[26px] font-bold text-text-primary">Create Account</h1>
            <p className="text-[14px] text-text-secondary mt-1">Join the FET Management Platform</p>
          </div>

          {error && <div className="bg-red-50 border border-red-200 text-red-700 px-4 py-3 rounded-xl text-[13px] mb-5 font-medium whitespace-pre-line">{error}</div>}
          {success && <div className="bg-green-50 border border-green-200 text-green-700 px-4 py-3 rounded-xl text-[13px] mb-5 whitespace-pre-line font-medium">{success}</div>}

          <form onSubmit={handleSubmit} className="space-y-4">
            <div>
              <label className={labelBase}>Full Name *</label>
              <div className="flex gap-2">
                <div className="relative flex-1">
                  <User className="absolute left-3 top-1/2 transform -translate-y-1/2 text-text-secondary" size={16} />
                  <input type="text" name="firstName" value={formData.firstName} onChange={handleChange}
                    placeholder="First name" className={`${inputBase} pl-10`} required />
                </div>
                <input type="text" name="lastName" value={formData.lastName} onChange={handleChange}
                  placeholder="Last name" className={inputBase} required />
              </div>
            </div>

            <div>
              <label className={labelBase}>Email *</label>
              <div className="relative">
                <Mail className="absolute left-3 top-1/2 transform -translate-y-1/2 text-text-secondary" size={16} />
                <input type="email" name="email" value={formData.email} onChange={handleChange}
                  placeholder="you@fet.edu" className={`${inputBase} pl-10`} required />
              </div>
            </div>

            <div>
              <label className={labelBase}>I am a *</label>
              <div className="grid grid-cols-2 gap-3">
                {[
                  { key: 'student', label: 'student', Icon: GraduationCap },
                  { key: 'lecturer', label: 'lecturer', Icon: Briefcase },
                ].map(({ key, label, Icon }) => (
                  <button key={key} type="button"
                    onClick={() => setFormData((prev) => ({ ...prev, accountType: key }))}
                    className={`px-4 py-3 rounded-xl border-2 flex items-center justify-center gap-2 capitalize font-medium text-[13px] transition-all ${
                      formData.accountType === key
                        ? 'border-primary bg-primary-light text-primary'
                        : 'border-border-default hover:border-primary/40 text-text-secondary'
                    }`}>
                    <Icon size={15} /> {label}
                  </button>
                ))}
              </div>
              {!isStudent && (
                <p className="text-[11px] text-text-secondary mt-1">
                  Lecturer accounts are reviewed by an administrator before teaching features unlock.
                </p>
              )}
            </div>

            {isStudent && (
              <>
                <div>
                  <label className={labelBase}>Department *</label>
                  <div className="relative">
                    <Building className="absolute left-3 top-1/2 transform -translate-y-1/2 text-text-secondary" size={16} />
                    <select name="department" value={formData.department} onChange={handleChange}
                      className={`${inputBase} pl-10`} required>
                      <option value="">-- Select Department --</option>
                      {departments.map((dept) => (
                        <option key={dept.id} value={dept.id}>
                          {dept.name}{dept.code ? ` (${dept.code})` : ''}
                        </option>
                      ))}
                    </select>
                  </div>
                </div>

                <div>
                  <label className={labelBase}>Matricule Number *</label>
                  <div className="relative">
                    <BookOpen className="absolute left-3 top-1/2 transform -translate-y-1/2 text-text-secondary" size={16} />
                    <input type="text" name="matricule" value={formData.matricule} onChange={handleChange}
                      placeholder="e.g., FE24A389" className={`${inputBase} pl-10 uppercase`} required />
                  </div>
                  <p className="text-[11px] text-text-secondary mt-1">Your unique student identification number</p>
                </div>

                <div>
                  <label className={labelBase}>Level *</label>
                  <div className="relative">
                    <GraduationCap className="absolute left-3 top-1/2 transform -translate-y-1/2 text-text-secondary" size={16} />
                    <select name="level" value={formData.level} onChange={handleChange}
                      className={`${inputBase} pl-10`} required>
                      <option value="">Select Level</option>
                      {['100', '200', '300', '400', '500', 'MSc', 'PhD'].map((lv) => (
                        <option key={lv} value={lv}>{lv === 'MSc' || lv === 'PhD' ? lv : `${lv} Level`}</option>
                      ))}
                    </select>
                  </div>
                </div>
              </>
            )}

            {!isStudent && (
              <div>
                <label className={labelBase}>Staff Number *</label>
                <div className="relative">
                  <Briefcase className="absolute left-3 top-1/2 transform -translate-y-1/2 text-text-secondary" size={16} />
                  <input type="text" name="staffid" value={formData.staffid} onChange={handleChange}
                    placeholder="e.g., STF-001" className={`${inputBase} pl-10 uppercase`} required />
                </div>
              </div>
            )}

            <div>
              <label className={labelBase}>Password * (min 8)</label>
              <div className="relative">
                <Lock className="absolute left-3 top-1/2 transform -translate-y-1/2 text-text-secondary" size={16} />
                <input type={showPassword ? 'text' : 'password'} name="password" value={formData.password} onChange={handleChange}
                  autoComplete="new-password" className={`${inputBase} pl-10 pr-11`} required />
                <button type="button" onClick={() => setShowPassword(!showPassword)} className="absolute right-3 top-1/2 text-text-secondary hover:text-text-primary">
                  {showPassword ? <EyeOff size={16} /> : <Eye size={16} />}
                </button>
              </div>
              <p className="text-[11px] text-text-secondary mt-1">
                Strength is checked by the server; your password is never stored in this browser.
              </p>
            </div>

            <div>
              <label className={labelBase}>Confirm Password *</label>
              <div className="relative">
                <Lock className="absolute left-3 top-1/2 transform -translate-y-1/2 text-text-secondary" size={16} />
                <input type={showConfirmPassword ? 'text' : 'password'} name="confirmPassword" value={formData.confirmPassword} onChange={handleChange}
                  autoComplete="new-password" className={`${inputBase} pl-10 pr-11`} required />
                <button type="button" onClick={() => setShowConfirmPassword(!showConfirmPassword)} className="absolute right-3 top-1/2 text-text-secondary hover:text-text-primary">
                  {showConfirmPassword ? <EyeOff size={16} /> : <Eye size={16} />}
                </button>
              </div>
            </div>

            <button type="submit" disabled={isLoading || Boolean(success)}
              className="fet-btn-primary w-full py-3 text-[14px] disabled:opacity-60 mt-2">
              {isLoading ? 'Creating account...' : 'Create Account'}
            </button>
          </form>

          <p className="text-center text-[13px] text-text-secondary mt-6">
            Already have an account? <button type="button" onClick={onSwitchToLogin} className="text-primary font-semibold hover:opacity-80">Sign in</button>
          </p>
        </div>
      </div>

      {/* Right: Visual Section */}
      <div className="hidden lg:flex flex-1 relative fet-tech-grid items-center justify-center">
        <div className="absolute inset-0 bg-gradient-to-br from-primary/20 to-transparent"></div>
        <div className="relative z-10 text-center px-12 max-w-lg">
          <div className="w-20 h-20 rounded-2xl flex items-center justify-center mx-auto mb-8" style={{ backgroundColor: 'rgba(63,53,181,0.3)', border: '1px solid rgba(63,53,181,0.2)' }}>
            <GraduationCap size={36} className="text-white" />
          </div>
          <h2 className="text-[28px] font-bold text-white leading-tight mb-4">
            Join FET Platform
          </h2>
          <p className="text-[15px] text-white/50 leading-relaxed">
            Register as a student or lecturer to access the complete engineering management experience.
          </p>
        </div>
      </div>
    </div>
  );
};

/** Turn an axios/envelope error into something a person can act on. */
const readableError = (err) => {
  const data = err?.response?.data;
  const message = data?.error?.message;
  if (typeof message === 'string' && message.trim()) return message;
  // DRF field errors arrive as {field: [msg]}; surface the first useful one.
  if (data && typeof data === 'object') {
    for (const [field, value] of Object.entries(data)) {
      if (field === 'error') continue;
      const first = Array.isArray(value) ? value[0] : value;
      if (typeof first === 'string' && first) return `${field}: ${first}`;
    }
  }
  return 'Registration failed. Please check your details.';
};

export default SignUp;