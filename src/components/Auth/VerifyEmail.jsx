import React, { useState } from 'react';
import { MailCheck, ArrowLeft, EyeOff, Eye } from 'lucide-react';
import { verifyEmail, resendVerification } from '../../api/auth';

/**
 * VerifyEmail — shown after registration or when a login attempt hits the
 * ACCOUNT_NOT_VERIFIED gate (BR-002/BR-209). Completing verification completes
 * the sign-in that was parked in memory.
 */
const VerifyEmail = ({ email, onVerified, onCancel }) => {
  const [code, setCode] = useState('');
  const [showCode, setShowCode] = useState(false);
  const [error, setError] = useState('');
  const [info, setInfo] = useState('');
  const [isLoading, setIsLoading] = useState(false);
  const [isResending, setIsResending] = useState(false);

  const handleVerify = async (e) => {
    e.preventDefault();
    setError('');
    setInfo('');
    if (code.trim().length < 4) {
      setError('Enter the verification code from your email.');
      return;
    }
    setIsLoading(true);
    try {
      await verifyEmail({ email, code: code.trim() });
      const result = await onVerified();
      if (!result?.success) {
        setError(result?.message || 'Verification succeeded but sign-in failed. Please log in.');
        setIsLoading(false);
      }
      // on success: App's handleVerified clears pendingVerify and logs in
    } catch (err) {
      setError(err.message || 'Verification failed. Request a new code and try again.');
      setIsLoading(false);
    }
  };

  const handleResend = async () => {
    setError('');
    setInfo('');
    setIsResending(true);
    try {
      await resendVerification({ email });
      setInfo('If that address is awaiting verification, a new code has been sent.');
    } catch (err) {
      setError(err.message || 'Could not resend the code.');
    } finally {
      setIsResending(false);
    }
  };

  return (
    <div className="min-h-screen flex items-center justify-center bg-page-bg p-6">
      <div className="w-full max-w-[400px]">
        <button
          onClick={onCancel}
          className="flex items-center gap-2 text-text-secondary hover:text-text-primary mb-8 transition-colors text-[13px] font-medium"
        >
          <ArrowLeft size={16} /> Back to Login
        </button>

        <div className="fet-card p-8">
          <div className="text-center mb-8">
            <div
              className="w-12 h-12 rounded-xl flex items-center justify-center mx-auto mb-4"
              style={{ backgroundColor: '#3F35B5' }}
            >
              <MailCheck size={22} className="text-white" />
            </div>
            <h1 className="text-[22px] font-bold text-text-primary">Verify your email</h1>
            <p className="text-[13px] text-text-secondary mt-2">
              We sent a code to <span className="font-semibold text-text-primary">{email}</span>
            </p>
          </div>

          {error && (
            <div className="bg-red-50 border border-red-200 text-red-700 px-4 py-3 rounded-xl text-[13px] mb-4 font-medium">
              {error}
            </div>
          )}
          {info && (
            <div className="bg-green-50 border border-green-200 text-green-700 px-4 py-3 rounded-xl text-[13px] mb-4 font-medium">
              {info}
            </div>
          )}

          <form onSubmit={handleVerify} className="space-y-4">
            <div>
              <label className="fet-label">Verification Code</label>
              <div className="relative">
                <input
                  type={showCode ? 'text' : 'password'}
                  value={code}
                  onChange={(e) => setCode(e.target.value)}
                  placeholder="Enter the 6-digit code"
                  className="fet-input pr-11 text-center tracking-widest font-semibold"
                  autoComplete="one-time-code"
                  inputMode="numeric"
                  required
                />
                <button
                  type="button"
                  onClick={() => setShowCode(!showCode)}
                  className="absolute right-3 top-1/2 -translate-y-1/2 text-text-secondary hover:text-text-primary"
                  aria-label={showCode ? 'Hide code' : 'Show code'}
                >
                  {showCode ? <EyeOff size={16} /> : <Eye size={16} />}
                </button>
              </div>
            </div>

            <button type="submit" disabled={isLoading} className="fet-btn-primary w-full py-3 text-[14px] disabled:opacity-60">
              {isLoading ? 'Verifying…' : 'Verify & Sign In'}
            </button>
          </form>

          <p className="text-center mt-5 text-[13px] text-text-secondary">
            Didn't get a code?{' '}
            <button
              onClick={handleResend}
              disabled={isResending}
              className="text-primary font-semibold hover:opacity-80 transition-opacity disabled:opacity-50"
            >
              {isResending ? 'Sending…' : 'Resend code'}
            </button>
          </p>
        </div>
      </div>
    </div>
  );
};

export default VerifyEmail;
