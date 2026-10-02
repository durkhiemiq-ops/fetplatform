import React, { useCallback, useEffect, useState } from 'react';
import { useAppContext } from '../../context/AppContext';
import {
  Calendar, Users, Clock, QrCode, Plus, X, Monitor, Square, Pencil, RefreshCw, ChevronDown, ClipboardList, ShieldAlert,
} from 'lucide-react';
import AttendanceSession from './AttendanceSession';
import QRScanner from './QRScanner';
import StationQR from './StationQR';
import AttendanceTable from './AttendanceTable';
import { getSessionDetail } from '../../api/attendance';

const STATUS_BADGE = {
  ACTIVE: 'fet-badge fet-badge-active',
  CLOSED: 'fet-badge fet-badge-inactive',
  EXPIRED: 'fet-badge fet-badge-danger',
};

function formatTime(value) {
  if (!value) return '—';
  const d = new Date(value);
  return Number.isNaN(d.getTime()) ? String(value) : d.toLocaleString();
}

/**
 * AttendanceDashboard — wired to the strict checkpoint backend.
 *
 * Students: scan a checkpoint QR (manual entry). Only the checkpoint's own
 * student can redeem its token (BR-039); history comes from /records/.
 *
 * Lecturers/admins: start a session, select checkpoints, project a fresh QR
 * per student (via StationQR), watch live marks, correct records (audited).
 */
const AttendanceDashboard = ({ user }) => {
  const {
    attendanceSessions,
    attendanceRecords,
    addAttendanceSession,
    closeAttendanceSession,
    getAttendanceForSession,
    listReviewFlags,
    recordAttendance,
    correctRecord,
  } = useAppContext();

  const userRole = (user?.role || 'STUDENT').toUpperCase();
  const isStudent = userRole === 'STUDENT';

  const [showCreate, setShowCreate] = useState(false);
  const [showScanner, setShowScanner] = useState(false);
  const [selectedSessionId, setSelectedSessionId] = useState(null);
  const [detail, setDetail] = useState(null);
  const [flags, setFlags] = useState([]);
  const [notice, setNotice] = useState(null);
  const [correctingRecord, setCorrectingRecord] = useState(null);
  const [correctionReason, setCorrectionReason] = useState('');
  const [correctionBusy, setCorrectionBusy] = useState(false);

  const refreshDetail = useCallback(async () => {
    if (!selectedSessionId) return;
    try {
      const data = await getSessionDetail(selectedSessionId);
      setDetail(data);
    } catch {
      setDetail(null);
    }
  }, [selectedSessionId]);

  useEffect(() => {
    if (isStudent || !selectedSessionId) return undefined;
    refreshDetail();
    const timer = setInterval(refreshDetail, 3000);
    return () => clearInterval(timer);
  }, [isStudent, selectedSessionId, refreshDetail]);

  useEffect(() => {
    if (isStudent) return;
    listReviewFlags().then(setFlags).catch(() => {});
  }, [isStudent]);

  const selectedSession = selectedSessionId
    ? attendanceSessions.find((s) => s.id === selectedSessionId) || null
    : null;

  const sessionRecords = selectedSessionId ? getAttendanceForSession(selectedSessionId) : [];

  const studentRows = isStudent
    ? attendanceRecords.map((r) => ({
        id: r.id,
        course_code: r.course_code,
        course_name: r.course_name,
        recorded_at: r.recorded_at,
        status: r.status,
        corrected: r.corrected,
      }))
    : [];

  const handleClose = async (session) => {
    if (!window.confirm('Close this attendance session?')) return;
    try {
      await closeAttendanceSession(session.id);
      setSelectedSessionId(null);
      setDetail(null);
      setNotice('Attendance session closed.');
      setTimeout(() => setNotice(null), 4000);
    } catch (err) {
      setNotice(err.message);
      setTimeout(() => setNotice(null), 5000);
    }
  };

  const handleCorrect = async (record) => {
    if (!correctionReason.trim() || correctionBusy) return;
    setCorrectionBusy(true);
    try {
      await correctRecord(record.id, correctionReason.trim());
      setCorrectionReason('');
      setCorrectingRecord(null);
      await refreshDetail();
    } catch (err) {
      setNotice(err.message);
    } finally {
      setCorrectionBusy(false);
    }
  };

  // ===== STUDENT VIEW =====
  if (isStudent) {
    return (
      <div className="space-y-6">
        <div className="fet-welcome-banner">
          <h2 className="text-2xl font-bold">Attendance</h2>
          <p className="text-[#8683BA] mt-1">Scan the QR code your lecturer projects to check in.</p>
        </div>

        <div className="fet-card p-6">
          <button onClick={() => setShowScanner(true)} className="w-full fet-btn-primary">
            <QrCode size={20} />
            Scan QR Code
          </button>
          <p className="mt-2 text-center text-xs text-text-secondary">
            Codes rotate every ~10 seconds and are single-use per student.
          </p>
        </div>

        <div className="fet-card overflow-hidden">
          <div className="p-6 border-b border-border-default">
            <h3 className="text-lg font-semibold text-text-primary">My attendance history</h3>
          </div>
          <div className="overflow-x-auto">
            <table className="fet-table">
              <thead>
                <tr>
                  <th>Course</th>
                  <th>Date</th>
                  <th>Status</th>
                </tr>
              </thead>
              <tbody>
                {studentRows.map((r) => (
                  <tr key={r.id}>
                    <td className="font-medium">{r.course_code}</td>
                    <td className="text-sm">{formatTime(r.recorded_at)}</td>
                    <td>
                      <span className={`fet-badge ${r.corrected ? 'fet-badge-warning' : 'fet-badge-present'}`}>
                        {r.corrected ? 'Corrected' : (r.status || 'PRESENT')}
                      </span>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          {studentRows.length === 0 && (
            <div className="text-center py-8 text-text-secondary">No attendance records found</div>
          )}
        </div>

        {showScanner && (
          <QRScanner
            session={null}
            user={user}
            onClose={() => setShowScanner(false)}
            onScan={() => {
              setNotice('Attendance recorded.');
              setTimeout(() => setNotice(null), 4000);
              setShowScanner(false);
            }}
          />
        )}
      </div>
    );
  }

  // ===== LECTURER / ADMIN VIEW =====
  return (
    <div className="space-y-6">
      {notice && (
        <div className="rounded-lg bg-[#E8F5E9] text-[#1B5E20] px-4 py-3 text-sm font-medium">
          {notice}
        </div>
      )}

      <div className="fet-welcome-banner">
        <div className="flex items-start justify-between flex-wrap gap-3">
          <div>
            <h2 className="text-2xl font-bold">Attendance Management</h2>
            <p className="text-[#8683BA] mt-1">Run live attendance sessions and issue rotating QR codes</p>
          </div>
          <button
            onClick={() => setShowCreate(true)}
            className="flex items-center gap-2 px-4 py-2 bg-white/10 hover:bg-white/20 rounded-xl text-white font-medium transition-colors"
          >
            <Plus size={18} /> Start session
          </button>
        </div>
      </div>

      {flags.length > 0 && (
        <div className="rounded-xl border border-amber-200 bg-amber-50 p-4">
          <h3 className="mb-2 flex items-center gap-2 text-sm font-semibold text-amber-900">
            <ShieldAlert size={16} /> Attendance requiring review ({flags.length})
          </h3>
          <ul className="space-y-1">
            {flags.map((flag) => (
              <li key={flag.id} className="text-xs text-amber-800">
                {flag.student_name} · {flag.reason || flag.failure_code || 'flagged'} · {new Date(flag.timestamp).toLocaleString()}
              </li>
            ))}
          </ul>
        </div>
      )}

      <div className="fet-card overflow-hidden">
        <div className="p-6 border-b border-border-default flex items-center justify-between">
          <h3 className="text-lg font-semibold text-text-primary">Sessions</h3>
        </div>
        {attendanceSessions.length === 0 ? (
          <div className="p-6 text-center text-text-secondary text-sm">
            No sessions yet. Start one to project check-in QR codes for your class.
          </div>
        ) : (
          <div className="overflow-x-auto">
            <table className="fet-table">
              <thead>
                <tr>
                  <th>Course</th>
                  <th>Started</th>
                  <th>Status</th>
                  <th>Marks</th>
                  <th>Checkpoints</th>
                  <th />
                </tr>
              </thead>
              <tbody>
                {attendanceSessions.map((s) => (
                  <tr key={s.id} className={selectedSessionId === s.id ? 'bg-primary-light/30' : ''}>
                    <td className="font-medium">
                      <button
                        type="button"
                        className="flex items-center gap-1 text-left hover:text-primary"
                        onClick={() => setSelectedSessionId(s.id)}
                      >
                        {s.course_code} — {s.course_name}
                        <ChevronDown size={14} className="opacity-50" />
                      </button>
                    </td>
                    <td className="text-sm">{formatTime(s.started_at)}</td>
                    <td><span className={STATUS_BADGE[s.status] || 'fet-badge fet-badge-inactive'}>{s.status}</span></td>
                    <td className="text-sm">{s.records}</td>
                    <td className="text-sm">{s.checkpoints}</td>
                    <td className="text-right">
                      {s.status === 'ACTIVE' && (
                        <button
                          type="button"
                          onClick={() => handleClose(s)}
                          className="inline-flex items-center gap-1 text-xs font-medium text-danger hover:underline"
                        >
                          <Square size={13} /> Close
                        </button>
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>

      {selectedSession && selectedSession.status === 'ACTIVE' && (
        <div className="fet-card p-6">
          <div className="flex items-center justify-between mb-4">
            <div>
              <p className="font-semibold text-text-primary">{selectedSession.course_code} — {selectedSession.course_name}</p>
              <p className="text-xs text-text-secondary">
                {detail ? `${detail.marked_count} marked · ${detail.total_checkpoints} checkpoints` : 'Loading…'}
              </p>
            </div>
            <button
              type="button"
              onClick={() => handleClose(selectedSession)}
              className="inline-flex items-center gap-1 rounded-lg border border-danger px-3 py-2 text-sm font-medium text-danger hover:bg-red-50"
            >
              <Square size={14} /> Close session
            </button>
          </div>

          {detail?.status === 'ACTIVE' ? (
            <>
              <StationQR session={detail} onRefresh={refreshDetail} />
              <div className="mt-6">
                <h4 className="mb-2 text-sm font-semibold text-text-primary flex items-center gap-2">
                  <ClipboardList size={16} /> Live marks ({detail.record_count})
                </h4>
                <AttendanceTable
                  records={(detail.records || []).map((r) => ({ ...r, course_code: detail.course_code }))}
                  empty="No one has checked in yet — the QR is waiting."
                  canCorrect={false}
                />
              </div>
            </>
          ) : (
            <p className="text-sm text-text-secondary">
              {detail ? 'This session has ended.' : 'Loading live session…'}
            </p>
          )}
        </div>
      )}

      {selectedSession && selectedSession.status !== 'ACTIVE' && (
        <div className="fet-card p-6">
          <h4 className="mb-2 text-sm font-semibold text-text-primary">Session records</h4>
          <div className="overflow-x-auto">
            <table className="fet-table">
              <thead>
                <tr>
                  <th>Student</th>
                  <th>Course</th>
                  <th>Recorded</th>
                  <th>Status</th>
                  <th>Correct</th>
                </tr>
              </thead>
              <tbody>
                {sessionRecords.map((record) => (
                  <React.Fragment key={record.id}>
                    <tr>
                      <td className="font-medium">{record.student_name}</td>
                      <td className="text-sm">{record.course_code}</td>
                      <td className="text-sm">{formatTime(record.recorded_at)}</td>
                      <td>
                        <span className={`fet-badge ${record.corrected ? 'fet-badge-warning' : 'fet-badge-present'}`}>
                          {record.corrected ? 'Corrected' : (record.status || 'PRESENT')}
                        </span>
                      </td>
                      <td>
                        <button
                          type="button"
                          onClick={() => setCorrectingRecord(record)}
                          className="inline-flex items-center gap-1 text-xs text-primary hover:underline"
                        >
                          <Pencil size={13} /> Correct
                        </button>
                      </td>
                    </tr>
                    {correctingRecord?.id === record.id && (
                      <tr>
                        <td colSpan={5} className="bg-page-bg">
                          <div className="flex flex-col gap-2 py-2 sm:flex-row sm:items-start">
                            <input
                              type="text"
                              value={correctionReason}
                              onChange={(e) => setCorrectionReason(e.target.value)}
                              placeholder="Reason for the correction (required — audited)"
                              className="fet-input flex-1"
                            />
                            <button
                              type="button"
                              disabled={correctionBusy || !correctionReason.trim()}
                              onClick={() => handleCorrect(record)}
                              className="fet-btn-primary disabled:opacity-50"
                            >
                              {correctionBusy ? 'Saving…' : 'Save correction'}
                            </button>
                          </div>
                        </td>
                      </tr>
                    )}
                  </React.Fragment>
                ))}
              </tbody>
            </table>
          </div>
          {sessionRecords.length === 0 && (
            <p className="text-center text-sm text-text-secondary py-6">No records in this session.</p>
          )}
        </div>
      )}

      {showCreate && (
        <AttendanceSession
          user={user}
          onClose={() => setShowCreate(false)}
          onCreated={(session) => {
            setShowCreate(false);
            setSelectedSessionId(session.id);
          }}
        />
      )}
    </div>
  );
};

export default AttendanceDashboard;
