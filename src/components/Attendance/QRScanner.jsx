import React, { useState } from 'react';
import { useAppContext } from '../../context/AppContext';
import { QrCode, X, CheckCircle, AlertCircle } from 'lucide-react';

const ERROR_HINTS = {
  TOKEN_EXPIRED: 'This QR code has expired. Ask your lecturer for a fresh one.',
  TOKEN_ALREADY_USED: 'You have already been marked — this code cannot be scanned twice.',
  INVALID_TOKEN: 'That is not a valid attendance code.',
  TOKEN_STUDENT_MISMATCH: 'This QR code belongs to a different student.',
  NOT_ELIGIBLE: 'Only enrolled students can scan this code.',
  SESSION_EXPIRED: 'This attendance session has ended.',
  ALREADY_MARKED: 'You are already marked for this session.',
  RATE_LIMITED: 'Too many attempts — wait a minute and try again.',
  UNAUTHENTICATED: 'Session expired. Please log in again.',
};

const QRScanner = ({ session, user, onClose, onScan }) => {
  const { recordAttendance } = useAppContext();
  const [scanning, setScanning] = useState(false);
  const [result, setResult] = useState(null);
  const [error, setError] = useState('');
  const [manualCode, setManualCode] = useState('');

  const doScan = async (token) => {
    if (!token.trim()) {
      setError('Please enter the attendance code');
      return;
    }
    setScanning(true);
    setError('');
    try {
      const response = await recordAttendance(token.trim());
      setResult({
        success: true,
        time: new Date().toLocaleTimeString(),
        status: 'PRESENT',
      });
      onScan && onScan(response);
    } catch (err) {
      setError(ERROR_HINTS[err.code] || err.message || 'Could not scan that code.');
    } finally {
      setScanning(false);
    }
  };

  const handleSimulateScan = () => doScan(manualCode.trim());

  const handleManualSubmit = (e) => {
    e.preventDefault();
    doScan(manualCode);
  };

  return (
    <div className="fixed inset-0 bg-black/50 backdrop-blur-sm flex items-center justify-center z-50 p-4">
      <div className="fet-card bg-white rounded-2xl shadow-modal max-w-md w-full p-6">
        <div className="flex items-center justify-between mb-4">
          <h3 className="text-xl font-bold text-text-primary">Scan QR Code</h3>
          <button onClick={onClose} className="p-1 hover:bg-page-bg rounded-lg">
            <X size={24} className="text-text-secondary" />
          </button>
        </div>

        {/* Result */}
        {result?.success ? (
          <div className="text-center py-6">
            <CheckCircle size={64} className="mx-auto text-success mb-4" />
            <h4 className="text-xl font-bold text-success">Attendance Recorded</h4>
            <p className="text-text-secondary">Time: {result.time}</p>
            <p className="text-text-secondary">
              Status: <span className="font-bold text-success">{result.status}</span>
            </p>
            <button onClick={onClose} className="mt-4 fet-btn-primary">
              Done
            </button>
          </div>
        ) : (
          <>
            <div className="border-2 border-dashed border-border-default rounded-xl p-8 text-center">
              <QrCode size={64} className="mx-auto text-primary" />
              <p className="text-text-secondary mt-2">
                Enter the exact code your lecturer projects, then tap Submit.
              </p>
            </div>

            <div className="mt-4">
              <form onSubmit={handleManualSubmit} className="flex gap-2">
                <input
                  type="text"
                  value={manualCode}
                  onChange={(e) => setManualCode(e.target.value)}
                  placeholder="Enter attendance code"
                  className="flex-1 fet-input uppercase"
                  autoFocus
                />
                <button type="submit" disabled={scanning} className="fet-btn-primary disabled:opacity-50">
                  {scanning ? 'Checking…' : 'Submit'}
                </button>
              </form>
            </div>

            {error && (
              <div className="mt-4 p-3 bg-red-50 border border-red-200 rounded-xl text-danger text-sm flex items-center gap-2">
                <AlertCircle size={18} />
                {error}
              </div>
            )}
          </>
        )}
      </div>
    </div>
  );
};

export default QRScanner;
