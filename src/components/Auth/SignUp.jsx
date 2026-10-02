import React, { useState, useEffect } from 'react';
import { Mail, Lock, Eye, EyeOff, User, UserPlus, ArrowLeft, Building, GraduationCap, BookOpen } from 'lucide-react';

const SignUp = ({ onSignUp, onSwitchToLogin }) => {
  const [showPassword, setShowPassword] = useState(false);
  const [showConfirmPassword, setShowConfirmPassword] = useState(false);
  const [departments, setDepartments] = useState([]);
  const [formData, setFormData] = useState({
    fullName: '',
    email: '',
    password: '',
    confirmPassword: '',
    role: 'student',
    department: '',
    level: '',
    matricule: '',
  });
  const [error, setError] = useState('');
  const [success, setSuccess] = useState('');
  const [isLoading, setIsLoading] = useState(false);

  useEffect(() => {
    const loadDepartments = () => {
      let depts = JSON.parse(localStorage.getItem('fet_departments') || '[]');
      if (depts.length === 0) {
        depts = [
          { id: 1, name: 'Computer Engineering', code: 'CE', coordinator: 'Dr. Alida Vance' },
          { id: 2, name: 'Civil Engineering', code: 'CVE', coordinator: 'Dr. Michael Brown' },
          { id: 3, name: 'Chemical & Petroleum Engineering', code: 'CHE', coordinator: 'Dr. Emily Davis' },
          { id: 4, name: 'Electrical & Electronic Engineering', code: 'EE', coordinator: 'Dr. David Wilson' },
          { id: 5, name: 'Mechanical & Industrial Engineering', code: 'ME', coordinator: 'Dr. Robert Johnson' },
        ];
        localStorage.setItem('fet_departments', JSON.stringify(depts));
      }
      setDepartments(depts);
    };
    loadDepartments();
  }, []);

  const handleChange = (e) => {
    const { name, value } = e.target;
    setFormData(prev => ({ ...prev, [name]: value }));
    setError('');
  };

  const handleSubmit = (e) => {
    e.preventDefault();
    setIsLoading(true);
    setError('');
    setSuccess('');

    if (!formData.fullName || !formData.email || !formData.password || !formData.department) {
      setError('Please fill in all required fields');
      setIsLoading(false);
      return;
    }
    if (formData.role === 'student') {
      if (!formData.matricule) { setError('Matricule number is required for students'); setIsLoading(false); return; }
      if (!formData.level) { setError('Please select your level'); setIsLoading(false); return; }
    }
    if (formData.password !== formData.confirmPassword) { setError('Passwords do not match'); setIsLoading(false); return; }
    if (formData.password.length < 6) { setError('Password must be at least 6 characters'); setIsLoading(false); return; }

    const users = JSON.parse(localStorage.getItem('fet_users') || '[]');
    if (users.find(u => u.email.toLowerCase() === formData.email.toLowerCase())) {
      setError('User with this email already exists'); setIsLoading(false); return;
    }
    if (formData.role === 'student') {
      const existingMatricule = users.find(u => u.matricule === formData.matricule.toUpperCase());
      if (existingMatricule) { setError(`Matricule ${formData.matricule} is already taken.`); setIsLoading(false); return; }
    }

    const matricule = formData.role === 'student' ? formData.matricule.toUpperCase() : '';
    const selectedDept = departments.find(d => d.name === formData.department);

    const newUser = {
      id: Date.now(),
      fullName: formData.fullName,
      email: formData.email.toLowerCase(),
      password: formData.password,
      role: formData.role,
      department: formData.department,
      level: formData.role === 'student' ? formData.level : '',
      matricule: matricule,
      createdAt: new Date().toISOString(),
    };

    users.push(newUser);
    localStorage.setItem('fet_users', JSON.stringify(users));

    const coordName = selectedDept?.coordinator || 'Not Assigned';
    setSuccess(`Welcome ${formData.fullName}!`);
    if (formData.role === 'student') {
      setSuccess(prev => prev + `\nMatricule: ${matricule} • Level ${formData.level}`);
    }
    setSuccess(prev => prev + `\nDepartment: ${formData.department} • Coordinator: ${coordName}`);

    setTimeout(() => { setIsLoading(false); onSignUp(newUser); }, 1500);
  };

  const inputBase = "fet-input";
  const labelBase = "fet-label";

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

          {error && <div className="bg-red-50 border border-red-200 text-red-700 px-4 py-3 rounded-xl text-[13px] mb-5 font-medium">{error}</div>}
          {success && <div className="bg-green-50 border border-green-200 text-green-700 px-4 py-3 rounded-xl text-[13px] mb-5 whitespace-pre-line font-medium">{success}</div>}

          <form onSubmit={handleSubmit} className="space-y-4">
            <div>
              <label className={labelBase}>Full Name *</label>
              <div className="relative">
                <User className="absolute left-3 top-1/2 transform -translate-y-1/2 text-text-secondary" size={16} />
                <input type="text" name="fullName" value={formData.fullName} onChange={handleChange}
                  placeholder="e.g., John Doe" className={`${inputBase} pl-10`} required />
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
                {['student', 'lecturer'].map((role) => (
                  <button key={role} type="button" onClick={() => setFormData(prev => ({ ...prev, role }))}
                    className={`px-4 py-3 rounded-xl border-2 capitalize font-medium text-[13px] transition-all ${
                      formData.role === role
                        ? 'border-primary bg-primary-light text-primary'
                        : 'border-border-default hover:border-primary/40 text-text-secondary'
                    }`}>
                    {role}
                  </button>
                ))}
              </div>
            </div>

            <div>
              <label className={labelBase}>Department *</label>
              <div className="relative">
                <Building className="absolute left-3 top-1/2 transform -translate-y-1/2 text-text-secondary" size={16} />
                <select name="department" value={formData.department} onChange={handleChange}
                  className={`${inputBase} pl-10`} required>
                  <option value="">-- Select Department --</option>
                  {departments.length > 0 ? (
                    departments.map(dept => (
                      <option key={dept.id} value={dept.name}>{dept.name} ({dept.code})</option>
                    ))
                  ) : (
                    <option value="" disabled>Loading departments...</option>
                  )}
                </select>
              </div>
            </div>

            {formData.role === 'student' && (
              <>
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
                    <select name="level" value={formData.level} onChange={handleChange} className={`${inputBase} pl-10`} required>
                      <option value="">Select Level</option>
                      <option value="100">100 Level</option>
                      <option value="200">200 Level</option>
                      <option value="300">300 Level</option>
                      <option value="400">400 Level</option>
                      <option value="500">500 Level</option>
                      <option value="MSc">MSc</option>
                      <option value="PhD">PhD</option>
                    </select>
                  </div>
                </div>
              </>
            )}

            <div>
              <label className={labelBase}>Password * (min 6)</label>
              <div className="relative">
                <Lock className="absolute left-3 top-1/2 transform -translate-y-1/2 text-text-secondary" size={16} />
                <input type={showPassword ? 'text' : 'password'} name="password" value={formData.password} onChange={handleChange}
                  className={`${inputBase} pl-10 pr-11`} required />
                <button type="button" onClick={() => setShowPassword(!showPassword)} className="absolute right-3 top-1/2 text-text-secondary hover:text-text-primary">
                  {showPassword ? <EyeOff size={16} /> : <Eye size={16} />}
                </button>
              </div>
            </div>

            <div>
              <label className={labelBase}>Confirm Password *</label>
              <div className="relative">
                <Lock className="absolute left-3 top-1/2 transform -translate-y-1/2 text-text-secondary" size={16} />
                <input type={showConfirmPassword ? 'text' : 'password'} name="confirmPassword" value={formData.confirmPassword} onChange={handleChange}
                  className={`${inputBase} pl-10 pr-11`} required />
                <button type="button" onClick={() => setShowConfirmPassword(!showConfirmPassword)} className="absolute right-3 top-1/2 text-text-secondary hover:text-text-primary">
                  {showConfirmPassword ? <EyeOff size={16} /> : <Eye size={16} />}
                </button>
              </div>
            </div>

            <button type="submit" disabled={isLoading}
              className="fet-btn-primary w-full py-3 text-[14px] disabled:opacity-60 mt-2">
              {isLoading ? 'Creating account...' : 'Create Account'}
            </button>
          </form>

          <p className="text-center text-[13px] text-text-secondary mt-6">
            Already have an account? <button onClick={onSwitchToLogin} className="text-primary font-semibold hover:opacity-80">Sign in</button>
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

export default SignUp;
