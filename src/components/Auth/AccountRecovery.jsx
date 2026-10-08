import React, { useState } from 'react';
import { ArrowLeft, Mail } from 'lucide-react';
import { publicApi } from '../../lib/auth';

const messageFor = (error) => error.response?.data?.error?.message || 'The request could not be completed. Please try again.';

const RecoveryFrame = ({ title, onBack, children }) => (
  <div className="min-h-screen flex items-center justify-center bg-page-bg p-6">
    <div className="fet-card p-6 md:p-8 w-full max-w-md space-y-5">
      <button type="button" onClick={onBack} className="flex items-center gap-2 text-sm text-text-secondary"><ArrowLeft size={16} /> Back to sign in</button>
      <div className="flex items-center gap-3"><Mail className="text-primary" size={24} /><h1 className="text-xl font-bold">{title}</h1></div>
      {children}
    </div>
  </div>
);

export const VerifyEmail = ({ initialEmail = '', pendingLecturer = false, onBack }) => {
  const [email, setEmail] = useState(initialEmail);
  const [code, setCode] = useState('');
  const [busy, setBusy] = useState(false);
  const [verified, setVerified] = useState(false);
  const [notice, setNotice] = useState('');
  const [error, setError] = useState('');
  const verify = async (event) => {
    event.preventDefault();
    setBusy(true); setError(''); setNotice('');
    try {
      await publicApi.verifyEmail({ email: email.trim(), code: code.trim() });
      setCode(''); setVerified(true);
    } catch (err) { setError(messageFor(err)); }
    finally { setBusy(false); }
  };
  const resend = async () => {
    setBusy(true); setError(''); setNotice('');
    try {
      const result = await publicApi.resendVerification(email.trim());
      setNotice(result.message);
      setCode('');
    } catch (err) { setError(messageFor(err)); }
    finally { setBusy(false); }
  };
  return (
    <RecoveryFrame title="Verify your email" onBack={onBack}>
      {error && <p role="alert" className="text-danger text-sm">{error}</p>}
      {notice && <p role="status" className="text-sm text-primary">{notice}</p>}
      {verified ? (
        <div className="space-y-4">
          <p role="status">Email verified. You can now sign in.{pendingLecturer ? ' Teaching access still requires administrator approval.' : ''}</p>
          <button onClick={onBack} className="fet-btn-primary w-full">Continue to sign in</button>
        </div>
      ) : (
        <form className="space-y-4" onSubmit={verify}>
          <p className="text-sm text-text-secondary">Enter the six-digit code sent to your email address.</p>
          <label className="fet-label" htmlFor="verification-email">Email</label>
          <input id="verification-email" type="email" autoComplete="email" className="fet-input" value={email} onChange={(event) => setEmail(event.target.value)} required />
          <label className="fet-label" htmlFor="verification-code">Verification code</label>
          <input id="verification-code" inputMode="numeric" autoComplete="one-time-code" pattern="[0-9]{6}" maxLength={6} className="fet-input" value={code} onChange={(event) => setCode(event.target.value)} required />
          <button disabled={busy} className="fet-btn-primary w-full">{busy ? 'Please wait...' : 'Verify email'}</button>
          <button type="button" disabled={busy || !email.trim()} onClick={resend} className="fet-btn-secondary w-full">Send a new code</button>
        </form>
      )}
    </RecoveryFrame>
  );
};

export const PasswordRecovery = ({ initialEmail = '', onBack }) => {
  const [email, setEmail] = useState(initialEmail);
  const [code, setCode] = useState('');
  const [password, setPassword] = useState('');
  const [confirmation, setConfirmation] = useState('');
  const [stage, setStage] = useState('request');
  const [busy, setBusy] = useState(false);
  const [notice, setNotice] = useState('');
  const [error, setError] = useState('');
  const requestCode = async (event) => {
    event?.preventDefault();
    setBusy(true); setError(''); setNotice('');
    try {
      const result = await publicApi.forgotPassword(email.trim());
      setNotice(result.message);
      setStage('reset'); setCode('');
    } catch (err) { setError(messageFor(err)); }
    finally { setBusy(false); }
  };
  const reset = async (event) => {
    event.preventDefault();
    setError(''); setNotice('');
    if (password !== confirmation) { setError('Passwords do not match.'); return; }
    setBusy(true);
    try {
      const result = await publicApi.resetPassword({ email: email.trim(), code: code.trim(), new_password: password });
      setPassword(''); setConfirmation(''); setCode('');
      setNotice(result.message); setStage('done');
    } catch (err) { setError(messageFor(err)); }
    finally { setBusy(false); }
  };
  return (
    <RecoveryFrame title="Reset your password" onBack={onBack}>
      {error && <p role="alert" className="text-danger text-sm">{error}</p>}
      {notice && <p role="status" className="text-sm text-primary">{notice}</p>}
      {stage === 'done' ? <button onClick={onBack} className="fet-btn-primary w-full">Sign in</button> : (
        <form className="space-y-4" onSubmit={stage === 'request' ? requestCode : reset}>
          <label className="fet-label" htmlFor="reset-email">Email</label>
          <input id="reset-email" type="email" autoComplete="email" className="fet-input" value={email} onChange={(event) => setEmail(event.target.value)} required />
          {stage === 'reset' && (
            <>
              <label className="fet-label" htmlFor="reset-code">Reset code</label>
              <input id="reset-code" inputMode="numeric" autoComplete="one-time-code" pattern="[0-9]{6}" maxLength={6} className="fet-input" value={code} onChange={(event) => setCode(event.target.value)} required />
              <label className="fet-label" htmlFor="reset-password">New password</label>
              <input id="reset-password" type="password" autoComplete="new-password" minLength={8} className="fet-input" value={password} onChange={(event) => setPassword(event.target.value)} required />
              <label className="fet-label" htmlFor="reset-confirmation">Confirm password</label>
              <input id="reset-confirmation" type="password" autoComplete="new-password" minLength={8} className="fet-input" value={confirmation} onChange={(event) => setConfirmation(event.target.value)} required />
            </>
          )}
          <button disabled={busy} className="fet-btn-primary w-full">{busy ? 'Please wait...' : stage === 'request' ? 'Send reset code' : 'Update password'}</button>
          {stage === 'reset' && <button type="button" disabled={busy || !email.trim()} onClick={requestCode} className="fet-btn-secondary w-full">Send a new code</button>}
        </form>
      )}
    </RecoveryFrame>
  );
};
