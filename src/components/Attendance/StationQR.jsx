import React, { useState, useEffect, useCallback } from 'react';
import { RefreshCw, Clock, Users, Loader2 } from 'lucide-react';
import attendanceApi from '../../lib/attendance';
import QRCodeDisplay from './QRCode';

// Re-roll well inside the 10s token TTL so a slow poll can never leave a
// dead code on screen (BR-035: codes are continuously replaced, not 60s).
const REFRESH_MS = 8000;

const StationQR = ({ sessionId, station }) => {
  const [timeLeft, setTimeLeft] = useState(0);
  const [token, setToken] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [scanStats, setScanStats] = useState(null);

  // Memoised on sessionId so the refresh effect below can depend on it without
  // tearing down and rebuilding the interval on every render.
  const fetchToken = useCallback(async () => {
    if (!sessionId) return;
    setError('');
    try {
      const data = await attendanceApi.myStationToken(sessionId);
      setToken(data.token);
      setTimeLeft(data.expires_in_seconds || 10);
      setScanStats({
        scans_at_station: data.scans_at_station,
        scans_remaining: data.scans_remaining,
        total_checked_in: data.total_checked_in,
        expected_headcount: data.expected_headcount,
      });
    } catch (err) {
      // If the window closed (or we are no longer a station), never keep
      // showing a dead QR.
      const code = err.response?.data?.error?.code;
      if (code === 'SESSION_EXPIRED' || code === 'FORBIDDEN') {
        setToken(null);
        setScanStats(null);
        setTimeLeft(0);
      }
      setError(err.response?.data?.error?.message || 'Could not load your station token.');
    } finally {
      setLoading(false);
    }
  }, [sessionId]);

  useEffect(() => {
    fetchToken();
    const timer = setInterval(fetchToken, REFRESH_MS);
    return () => clearInterval(timer);
  }, [fetchToken]);

  useEffect(() => {
    const tick = setInterval(() => {
      setTimeLeft((t) => Math.max(0, t - 1));
    }, 1000);
    return () => clearInterval(tick);
  }, []);

  const courseCode = station?.course_code || 'Course';
  const className = station?.class_name || '—';

  return (
    <div className="mt-4 p-4 bg-gradient-to-r from-[#0F0B3D] to-[#3F35B5] rounded-xl text-white">
      <div className="flex items-center justify-between mb-3">
        <div className="flex items-center gap-2">
          <Users size={18} />
          <span className="font-semibold">YOU ARE A QR STATION</span>
        </div>
        <div className="flex items-center gap-2">
          <Clock size={16} />
          <span className="font-mono font-bold">{timeLeft}s</span>
        </div>
      </div>

      {error && <p className="text-xs text-red-200 mb-2">{error}</p>}

      <div className="bg-white qr-sheet rounded-xl p-6 text-center">
        {loading ? (
          <div className="flex justify-center py-8">
            <Loader2 className="h-8 w-8 animate-spin text-primary" />
          </div>
        ) : token ? (
          <QRCodeDisplay value={token} size={160} className="mx-auto rounded-lg" />
        ) : (
          <p className="text-text-secondary text-sm py-8">No token yet — share this screen with classmates.</p>
        )}
        <p className="text-text-secondary font-mono text-xs mt-2 break-all">{token || ''}</p>
        <p className="text-xs text-text-secondary mt-1">Students scan this QR to mark attendance</p>
      </div>

      {scanStats && (
        <div className="mt-3 flex justify-between text-xs text-white/80">
          <span>Scanned at your station: <span className="font-bold">{scanStats.scans_at_station}</span></span>
          {scanStats.scans_remaining !== null && scanStats.scans_remaining !== undefined && (
            <span>Scans left: <span className="font-bold">{scanStats.scans_remaining}</span></span>
          )}
          <span>Checked in: <span className="font-bold">{scanStats.total_checked_in}</span></span>
        </div>
      )}

      <div className="flex items-center justify-between mt-4">
        <p className="text-sm text-white/80">
          {courseCode} · {className}
        </p>
        <button
          onClick={fetchToken}
          disabled={loading}
          className="flex items-center gap-2 px-4 py-2 bg-white/20 hover:bg-white/30 rounded-lg text-sm font-medium transition-colors"
        >
          <RefreshCw size={16} />
          Refresh QR
        </button>
      </div>

      <p className="text-xs text-white/60 mt-3 text-center">
        Your device is currently acting as an attendance station
      </p>
    </div>
  );
};

export default StationQR;