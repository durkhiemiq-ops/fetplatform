import React, { useState } from 'react';
import { authApi } from '../../lib/auth';
import { PasswordRecovery } from './AccountRecovery';
import { Eye, EyeOff, ArrowRight, GraduationCap } from 'lucide-react';

const Login = ({ onLogin, onSwitchToSignUp }) => {
  const [journey, setJourney] = useState('login');
  const [identifier, setIdentifier] = useState('');
  const [password, setPassword] = useState('');
  const [showPassword, setShowPassword] = useState(false);
  const [error, setError] = useState('');
  const [isLoading, setIsLoading] = useState(false);

  const handleSubmit = async (e) => {
    e.preventDefault();
    setError('');
    setIsLoading(true);

    const id = identifier.trim();

    if (!id || !password) {
      setError('Please enter your email address and password.');
      setIsLoading(false);
      return;
    }

    try {
      const payload = { email: id, password };
      const response = await authApi.login(payload);
      // Tokens are set as httpOnly cookies by the backend — JS never sees them.
      const user = response.data?.data ?? response.data;

      // Identity is handed to App, which publishes it through SessionProvider.
// Nothing is cached in localStorage — the httpOnly session cookie decides
      // whether the session exists (AGENTS.md).
      setIsLoading(false);
      onLogin(user);
    } catch (err) {
      setIsLoading(false);
      if (err.response?.data?.error?.message) {
        setError(err.response.data.error.message);
      } else if (err.response?.data?.message) {
        setError(err.response.data.message);
      } else {
        setError('Invalid credentials. Please check and try again.');
      }
    }
  };

  if (journey === 'reset') return <PasswordRecovery initialEmail={identifier} onBack={() => setJourney('login')} />;

  return (
    <div className="min-h-screen flex">
      {/* Left: Login Form */}
      <div className="flex-1 flex items-center justify-center p-6 bg-surface">
        <div className="w-full max-w-[400px]">
          {/* Logo */}
          <div className="flex items-center gap-3 mb-10">
            <div className="w-11 h-11 rounded-xl flex items-center justify-center" style={{ backgroundColor: '#3F35B5' }}>
              <span className="text-white font-bold text-lg">FET</span>
            </div>
            <div>
              <h1 className="text-[17px] font-bold text-text-primary leading-tight">FET Platform</h1>
              <p className="text-[11px] text-text-secondary font-medium">Engineering Management</p>
            </div>
          </div>

          {/* Welcome */}
          <div className="mb-8">
            <h2 className="text-[28px] font-bold text-text-primary leading-tight">Welcome back</h2>
            <p className="text-[14px] text-text-secondary mt-1.5">Sign in to your account to continue</p>
          </div>

          {error && (
            <div className="bg-red-50 border border-red-200 text-red-700 px-4 py-3 rounded-xl text-[13px] mb-5 font-medium">
              {error}
            </div>
          )}

          <form onSubmit={handleSubmit} className="space-y-5">
            <div>
              <label htmlFor="identifier" className="fet-label">
                Email
              </label>
              <input
                id="identifier"
                type="email"
                autoComplete="email"
                placeholder="you@example.edu"
                value={identifier}
                onChange={(e) => setIdentifier(e.target.value)}
                className="fet-input"
                required
              />
            </div>

            <div>
              <label htmlFor="password" className="fet-label">
                Password
              </label>
              <div className="relative">
                <input
                  id="password"
                  type={showPassword ? 'text' : 'password'}
                  placeholder="Enter your password"
                  value={password}
                  onChange={(e) => setPassword(e.target.value)}
                  className="fet-input pr-11"
                  required
                />
                <button
                  type="button"
                  onClick={() => setShowPassword(!showPassword)}
                  className="absolute right-3 top-1/2 transform -translate-y-1/2 text-text-secondary hover:text-text-primary transition-colors"
                  aria-label={showPassword ? 'Hide password' : 'Show password'}
                >
                  {showPassword ? <EyeOff size={17} /> : <Eye size={17} />}
                </button>
              </div>
            </div>

            <button 
              type="submit" 
              disabled={isLoading}
              className="fet-btn-primary w-full py-3 text-[14px] disabled:opacity-60"
            >
              {isLoading ? (
                <div className="flex items-center gap-2">
                  <div className="w-4 h-4 border-2 border-white border-t-transparent rounded-full animate-spin"></div>
                  Signing in...
                </div>
              ) : (
                <>
                  Sign In
                  <ArrowRight size={16} />
                </>
              )}
            </button>
          </form>

          <p className="text-center mt-6 text-[13px] text-text-secondary">
            Don&apos;t have an account?{' '}
            <button type="button" onClick={onSwitchToSignUp} className="text-primary font-semibold hover:opacity-80 transition-opacity">Register</button>
          </p>

          <div className="mt-6 flex justify-center text-sm">
            <button type="button" onClick={() => { setPassword(''); setJourney('reset'); }} className="text-primary hover:underline">Forgot password?</button>
          </div>
        </div>
      </div>

      {/* Right: Visual Section */}
      <div className="hidden lg:flex flex-1 relative fet-tech-grid items-center justify-center">
        {/* Overlay for slight depth */}
        <div className="absolute inset-0 bg-gradient-to-br from-primary/20 to-transparent"></div>
        
        {/* Content */}
        <div className="relative z-10 text-center px-12 max-w-lg">
          <div className="w-20 h-20 rounded-2xl flex items-center justify-center mx-auto mb-8" style={{ backgroundColor: 'rgba(63,53,181,0.3)', border: '1px solid rgba(63,53,181,0.2)' }}>
            <GraduationCap size={36} className="text-white" />
          </div>
          <h2 className="text-[28px] font-bold text-white leading-tight mb-4">
            Faculty of Engineering<br/>& Technology
          </h2>
          <p className="text-[15px] text-white/50 leading-relaxed">
            Academic, Learning & Project Management Platform. Manage courses, track attendance, collaborate on projects, and monitor your academic progress.
          </p>
          <div className="flex items-center justify-center gap-8 mt-10">
            <div className="text-center">
              <p className="text-[24px] font-bold text-white">5</p>
              <p className="text-[11px] text-white/40 font-medium uppercase tracking-wider">Departments</p>
            </div>
            <div className="w-px h-8 bg-white/10"></div>
            <div className="text-center">
              <p className="text-[24px] font-bold text-white">18+</p>
              <p className="text-[11px] text-white/40 font-medium uppercase tracking-wider">Courses</p>
            </div>
            <div className="w-px h-8 bg-white/10"></div>
            <div className="text-center">
              <p className="text-[24px] font-bold text-white">100%</p>
              <p className="text-[11px] text-white/40 font-medium uppercase tracking-wider">Digital</p>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
};

export default Login;
