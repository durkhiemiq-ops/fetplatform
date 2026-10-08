import React, { useState, useEffect, useCallback, useMemo } from 'react';
import {
  Calendar, Clock, QrCode, Plus,
  Eye, X, Monitor, Square, Loader2, RefreshCw, Pencil, AlertCircle,
  UserCheck, Search, ChevronDown, CheckCircle2, ClipboardCheck, Users,
} from 'lucide-react';
import attendanceApi from '../../lib/attendance';
import AttendanceSession from './AttendanceSession';
import QRScanner from './QRScanner';
import StationQR from './StationQR';
import QRCodeDisplay from './QRCode';
import {
  SectionHeader, Card, CardHead, CardBody, CardFoot, Eyebrow, Pill, Tag, Callout, EmptyState,
} from '../UI';

/** The searchable roster used when picking students to act as QR stations. */
const StationPickerBody = ({ roster, picked, onToggle, onSave, saving }) => {
  const [term, setTerm] = useState('');
  const q = term.trim().toLowerCase();
  const visible = roster.filter((s) => (
    !q
    || (s.full_name || '').toLowerCase().includes(q)
    || (s.email || '').toLowerCase().includes(q)
    || (s.student_number || '').toLowerCase().includes(q)
  ));

  return (
    <div>
      <div className="relative mb-2">
        <Search size={15} className="absolute left-3 top-1/2 -translate-y-1/2 text-text-muted" />
        <input
          type="text"
          value={term}
          onChange={(e) => setTerm(e.target.value)}
          placeholder="Search by name, matricule or email"
          className="fet-input pl-9"
        />
      </div>

      {roster.length === 0 ? (
        <p className="py-4 text-center text-[12.5px] text-text-secondary">
          No students are enrolled in this class yet.
        </p>
      ) : (
        <>
          <div className="mb-2 flex items-center justify-between">
            <span className="text-[11.5px] text-text-secondary">
              {picked.length} selected
              {q ? ` · ${visible.length} match "${term}"` : ` · ${visible.length} available`}
            </span>
            <div className="flex gap-3">
              <button type="button" onClick={() => visible.forEach((s) => onToggle(s.id))} className="text-[11.5px] text-primary hover:underline">
                Select all
              </button>
              <button type="button" onClick={() => visible.forEach((s) => { if (picked.includes(s.id)) onToggle(s.id); })} className="text-[11.5px] text-text-secondary hover:underline">
                Clear
              </button>
            </div>
          </div>

          <div className="max-h-56 space-y-1 overflow-y-auto pr-1">
            {visible.length === 0 ? (
              <p className="py-4 text-center text-[12.5px] text-text-secondary">
                No student matches that search.
              </p>
            ) : visible.map((s) => (
              <label
                key={s.id}
                className="flex cursor-pointer items-center gap-3 rounded-md border border-border-default bg-surface p-2 transition-colors hover:border-primary"
              >
                <input
                  type="checkbox"
                  checked={picked.includes(s.id)}
                  onChange={() => onToggle(s.id)}
                  className="h-4 w-4 accent-primary"
                />
                <span className="min-w-0 flex-1">
                  <span className="block truncate text-[13px] font-medium text-text-primary">{s.full_name}</span>
                  <span className="mono block truncate text-[11.5px] text-text-secondary">
                    {s.student_number || 'no matricule'}
                  </span>
                </span>
              </label>
            ))}
          </div>

          <div className="mt-3 flex justify-end gap-2">
            <button type="button" onClick={onSave} disabled={saving || picked.length === 0} className="fet-btn-primary">
              {saving ? <Loader2 size={14} className="animate-spin" /> : <UserCheck size={14} />}
              Assign {picked.length || ''} station{picked.length === 1 ? '' : 's'}
            </button>
          </div>
        </>
      )}
    </div>
  );
};

const getRole = (user) => (user?.role || 'student').toLowerCase();
const isLecturerRole = (user) => {
  const r = getRole(user);
  return r === 'lecturer' || r === 'admin' || r.endsWith('_admin');
};
const secondsLeft = (ms, now) => Math.max(0, Math.round((ms - now) / 1000));
const fmtDate = (iso) => (iso ? new Date(iso).toLocaleDateString() : '');
const fmtTime = (iso) => (iso ? new Date(iso).toLocaleTimeString() : '');

const getStatusColor = (status) => {
  switch (status) {
    case 'ACTIVE': return 'fet-badge fet-badge-active';
    case 'CLOSED': return 'fet-badge fet-badge-inactive';
    case 'EXPIRED': return 'fet-badge fet-badge-danger';
    default: return 'fet-badge fet-badge-inactive';
  }
};
const getRecordStatusColor = (status) => {
  switch (status) {
    case 'PRESENT': return 'fet-badge fet-badge-present';
    case 'LATE': return 'fet-badge fet-badge-late';
    case 'ABSENT': return 'fet-badge fet-badge-absent';
    default: return 'fet-badge fet-badge-absent';
  }
};

/* ---------------------------- STUDENT VIEW ---------------------------- */
const StudentAttendance = ({ user }) => {
  const [station, setStation] = useState(null);
  const [history, setHistory] = useState([]);
  const [loading, setLoading] = useState(true);
  const [showScanner, setShowScanner] = useState(false);
  const [error, setError] = useState('');
  const [now, setNow] = useState(Date.now());

  const load = useCallback(async () => {
    try {
      const [stationData, historyData] = await Promise.all([
        attendanceApi.myStation(),
        attendanceApi.myAttendance(),
      ]);
      setStation(stationData || null);
      setHistory(Array.isArray(historyData) ? historyData : []);
      setError('');
    } catch (err) {
      // Any failure must not leave a stale station banner on screen.
      setStation(null);
      setError(err.response?.data?.error?.message || 'Could not load attendance data.');
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    load();
    const timer = setInterval(load, 8000);
    return () => clearInterval(timer);
  }, [load]);

  // Tick every second so an expired station drops the banner immediately,
  // not up to 8s later on the next poll.
  useEffect(() => {
    const t = setInterval(() => setNow(Date.now()), 1000);
    return () => clearInterval(t);
  }, []);

  // Only treat the station as live while its attendance window is still open.
  // Requires a real station object with a session id, so a stray/truthy
  // payload can never render the banner.
  const liveStation = (() => {
    if (!station || typeof station !== 'object' || !station.attendance_session_id) return null;
    if (!station.session_expires_at) return station;
    return now < new Date(station.session_expires_at).getTime() ? station : null;
  })();

  return (
    <div className="space-y-6">
      <div className="fet-welcome-banner">
        <h2 className="text-2xl font-bold">Attendance</h2>
        <p className="text-[#8683BA] mt-1">Mark your attendance</p>
        <p className="text-[#8683BA] text-xs mt-1">Scan the QR code displayed by your lecturer</p>
      </div>

      {error && (
        <div className="bg-red-50 border border-red-200 text-danger px-4 py-3 rounded-xl text-sm">{error}</div>
      )}

      {liveStation && liveStation.attendance_session_id && (
        <StationQR sessionId={liveStation.attendance_session_id} station={liveStation} />
      )}

      <div className="fet-card p-6">
        <div className="flex items-center justify-between flex-wrap gap-4">
          <div>
            <h3 className="text-lg font-bold text-text-primary">Check-in now</h3>
            <p className="text-sm text-text-secondary">
              {liveStation ? 'You are a station: classmates scan your QR.' : 'Scan the QR your lecturer is showing to record your presence.'}
            </p>
          </div>
          {!liveStation && (
            <button onClick={() => setShowScanner(true)} className="fet-btn-primary">
              <QrCode size={20} /> Scan QR Code
            </button>
          )}
        </div>
      </div>

      {/* One honest summary card: the MVP has no points surface to show. */}
      <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
        <div className="fet-card p-5">
          <div className="flex items-center gap-3">
            <Calendar size={24} className="text-primary" />
            <div>
              <p className="text-sm font-semibold text-text-primary">{history.length}</p>
              <p className="text-xs text-text-secondary">Sessions attended</p>
            </div>
          </div>
        </div>
      </div>

      <div className="fet-card overflow-hidden">
        <div className="p-6 border-b border-border-default">
          <h3 className="text-lg font-semibold text-text-primary">Attendance History</h3>
        </div>
        <div className="overflow-x-auto">
          {loading ? (
            <div className="flex justify-center py-10">
              <Loader2 size={28} className="animate-spin text-primary" />
            </div>
          ) : (
            <table className="fet-table">
              <thead>
                <tr>
                  <th>Course</th>
                  <th>Class</th>
                  <th>Date</th>
                  <th>Status</th>
                  <th>Time</th>
                </tr>
              </thead>
              <tbody>
                {history.map((record, i) => (
                  <tr key={record.id || i}>
                    <td className="font-medium">{record.course_code}</td>
                    <td>{record.class_name}</td>
                    <td>{fmtDate(record.recorded_at) || record.session_date}</td>
                    <td><span className={getRecordStatusColor(record.status)}>{record.status}</span></td>
                    <td>{fmtTime(record.recorded_at)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
          {!loading && history.length === 0 && (
            <div className="text-center py-8 text-text-secondary">No attendance records yet</div>
          )}
        </div>
      </div>

      {showScanner && <QRScanner onClose={() => setShowScanner(false)} onScan={() => load()} />}
    </div>
  );
};

/* ---------------------------- LECTURER VIEW ---------------------------- */
const LecturerAttendance = () => {
  const [now, setNow] = useState(Date.now());
  const [sessions, setSessions] = useState([]);
  const [records, setRecords] = useState({});
  const [checkpoints, setCheckpoints] = useState({});
  const [showCreateSession, setShowCreateSession] = useState(false);
  const [selectedSession, setSelectedSession] = useState(null);
  const [showProjector, setShowProjector] = useState(false);
  const [projectorToken, setProjectorToken] = useState(null);
  const [projectorStudent, setProjectorStudent] = useState('');
  const [projectorError, setProjectorError] = useState('');
  const [projectorRemaining, setProjectorRemaining] = useState(0);
  const [projectorExpiresIn, setProjectorExpiresIn] = useState(10);
  const [autoSelecting, setAutoSelecting] = useState(false);
  const [stationPickerFor, setStationPickerFor] = useState(null);
  const [roster, setRoster] = useState([]);
  const [rosterLoading, setRosterLoading] = useState(false);
  const [pickedStations, setPickedStations] = useState([]);
  const [savingStations, setSavingStations] = useState(false);
  const [removingStation, setRemovingStation] = useState(null);
  const [rosterError, setRosterError] = useState('');
  const [correctingRecord, setCorrectingRecord] = useState(null);
  const [correctionStatus, setCorrectionStatus] = useState('PRESENT');
  const [correctionReason, setCorrectionReason] = useState('');
  const [flash, setFlash] = useState('');

  useEffect(() => {
    const timer = setInterval(() => setNow(Date.now()), 1000);
    return () => clearInterval(timer);
  }, []);

  // Restore the lecturer's sessions after a reload so Project / View stay available.
  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        const data = await attendanceApi.mySessions();
        if (cancelled || !Array.isArray(data)) return;
        setSessions((prev) => {
          const merged = new Map(prev.map((s) => [s.id, s]));
          data.forEach((s) => {
            if (!merged.has(s.id)) merged.set(s.id, s);
          });
          return Array.from(merged.values());
        });
        const live = data.find((s) => s.is_active);
        if (live) {
          loadCheckpoints(live.id);
        }
      } catch {
        // Not fatal: the lecturer can still start a new session.
      }
    })();
    return () => { cancelled = true; };
  }, []);

  const refreshStatus = useCallback(async (id) => {
    try {
      const st = await attendanceApi.status(id);
      setSessions((prev) => prev.map((s) => (s.id === id ? { ...s, ...st, status: st.status } : s)));
    } catch {
      // session may have expired server-side
    }
  }, []);

  // Poll live status of active sessions
  useEffect(() => {
    const active = sessions.filter((s) => s.status === 'ACTIVE');
    if (active.length === 0) return undefined;
    const timer = setInterval(() => {
      active.forEach((s) => refreshStatus(s.id));
    }, 3000);
    return () => clearInterval(timer);
  }, [sessions, refreshStatus]);

  // Rotate projector token
  useEffect(() => {
    if (!showProjector || !selectedSession) return undefined;
    let cancelled = false;
    const rotate = async () => {
      try {
        const data = await attendanceApi.generateTokens(selectedSession.id);
        if (cancelled) return;
        const first = data?.tokens?.[0];
        if (first?.token) {
          setProjectorToken(first.token);
          setProjectorStudent(first.student_name || '');
          setProjectorError('');
          setProjectorExpiresIn(data.expires_in_seconds || 10);
        } else {
          setProjectorError('The server returned no QR code. Try starting the session again.');
        }
      } catch (err) {
        if (cancelled) return;
        const code = err.response?.data?.error?.code;
        setProjectorToken(null);
        setProjectorError(
          code === 'SESSION_EXPIRED'
            ? 'The attendance window has closed. Close the projector and start a new session.'
            : err.response?.data?.error?.message || 'Could not load the QR code.',
        );
      }
    };
    rotate();
    const interval = setInterval(rotate, 8000);
    return () => { cancelled = true; clearInterval(interval); };
  }, [showProjector, selectedSession]);

  // Countdown to the moment the attendance window closes.
  useEffect(() => {
    if (!showProjector || !selectedSession) return undefined;
    const expiresAt = selectedSession.expires_at ? new Date(selectedSession.expires_at).getTime() : null;
    if (!expiresAt) return undefined;
    const tick = () => setProjectorRemaining(expiresAt - Date.now());
    tick();
    const t = setInterval(tick, 1000);
    return () => clearInterval(t);
  }, [showProjector, selectedSession]);

  const loadRecords = async (session) => {
    try {
      const data = await attendanceApi.sessionRecords(session.id);
      setRecords((prev) => ({ ...prev, [session.id]: Array.isArray(data) ? data : [] }));
    } catch {
      setRecords((prev) => ({ ...prev, [session.id]: [] }));
    }
  };

  const loadCheckpoints = async (sessionIdApi) => {
    try {
      const data = await attendanceApi.checkpoints(sessionIdApi);
      setCheckpoints((prev) => ({ ...prev, [sessionIdApi]: Array.isArray(data) ? data : [] }));
    } catch {
      setCheckpoints((prev) => ({ ...prev, [sessionIdApi]: [] }));
    }
  };

  const handleSessionCreated = (session) => {
    setSessions((prev) => [session, ...prev]);
    setFlash(`Attendance session started for ${session.course_code}.`);
    setTimeout(() => setFlash(''), 4000);
    setSelectedSession(session);
    loadCheckpoints(session.id);
  };

  const handleCloseSession = async (session) => {
    if (!window.confirm('Close this attendance session?')) return;
    try {
      const updated = await attendanceApi.closeSession(session.id);
      setSessions((prev) => prev.map((s) => (s.id === session.id ? { ...s, ...updated, status: 'CLOSED' } : s)));
      setSelectedSession(null);
      setShowProjector(false);
      setFlash('Attendance session closed.');
      setTimeout(() => setFlash(''), 3000);
    } catch (err) {
      alert(err.response?.data?.error?.message || 'Could not close the session.');
    }
  };

  const openStationPicker = async (session) => {
    if (stationPickerFor === session.id && !rosterLoading) {
      setStationPickerFor(null);
      return;
    }
    setStationPickerFor(session.id);
    setRosterError('');
    // Watchdog: never let the spinner outlive the request, even if the
    // response never arrives (blocked request, dropped connection, etc).
    let guard;
    try {
      setRosterLoading(true);
      guard = setTimeout(() => {
        setRosterLoading(false);
        setRosterError('The roster request did not respond. Check your connection and try again.');
      }, 10000);
      const data = await attendanceApi.eligibleStudents(session.id);
      setRoster(Array.isArray(data) ? data : []);
    } catch (err) {
      setRoster([]);
      setRosterError(
        err.response?.data?.error?.message
        || (err.code === 'ERR_NETWORK'
          ? 'Could not reach the server. Is the backend running on port 8000?'
          : err.message)
        || 'Could not load the class roster.',
      );
    } finally {
      if (guard) clearTimeout(guard);
      setRosterLoading(false);
    }
  };

  const toggleStation = (studentId) => {
    setPickedStations((prev) => (
      prev.includes(studentId)
        ? prev.filter((id) => id !== studentId)
        : [...prev, studentId]
    ));
  };

  const saveStations = async (session) => {
    if (pickedStations.length === 0) return;
    setSavingStations(true);
    try {
      await attendanceApi.createCheckpoints(session.id, pickedStations);
      setPickedStations([]);
      setStationPickerFor(null);
      setFlash(`${pickedStations.length} student${pickedStations.length === 1 ? '' : 's'} assigned as station${pickedStations.length === 1 ? '' : 's'}.`);
      setTimeout(() => setFlash(''), 4000);
      loadCheckpoints(session.id);
    } catch (err) {
      alert(err.response?.data?.error?.message || 'Could not assign the stations.');    } finally {
      setSavingStations(false);
    }
  };

  const removeStation = async (session, checkpoint) => {
    if (!window.confirm(`Remove ${checkpoint.student_name} as a station?`)) return;
    setRemovingStation(checkpoint.id);
    try {
      await attendanceApi.removeCheckpoint(session.id, checkpoint.id);
      loadCheckpoints(session.id);
    } catch (err) {
      alert(err.response?.data?.error?.message || 'Could not remove that station.');
    } finally {
      setRemovingStation(null);
    }
  };

  const handleAutoSelect = async (session) => {
    setAutoSelecting(true);
    try {
      await attendanceApi.autoSelectStations(session.id, 3);
      loadCheckpoints(session.id);
    } catch (err) {
      alert(err.response?.data?.error?.message || 'Could not auto-select stations.');
    } finally {
      setAutoSelecting(false);
    }
  };

  const handleCorrect = async (record) => {
    try {
      const updated = await attendanceApi.correctRecord(record.id, {
        status: correctionStatus,
        reason: correctionReason.trim(),
      });
      const sessId = record.attendance_session;
      setRecords((prev) => ({
        ...prev,
        [sessId]: (prev[sessId] || []).map((r) => (r.id === updated.id ? { ...r, status: updated.status } : r)),
      }));
      setCorrectingRecord(null);
      setCorrectionReason('');
      setFlash('Attendance record corrected.');
      setTimeout(() => setFlash(''), 3000);
    } catch (err) {
      alert(err.response?.data?.error?.message || 'Could not correct the record.');
    }
  };


  const displaySessions = useMemo(() => {
    // One row per class: the newest still-running session, else the newest
    // finished one. Prevents a pile of dead sessions for the same class.
    const best = new Map();
    sessions.forEach((s) => {
      const key = s.class_session_id || s.class_session || s.course_code;
      const current = best.get(key);
      if (!current) { best.set(key, s); return; }
      const currentLive = current.status === 'ACTIVE' && new Date(current.expires_at) > now;
      const candidateLive = s.status === 'ACTIVE' && new Date(s.expires_at) > now;
      if (candidateLive && !currentLive) best.set(key, s);
    });
    return Array.from(best.values())
      .filter((s) => s.status === 'ACTIVE' && new Date(s.expires_at) > now)
      .sort((a, b) => new Date(b.expires_at) - new Date(a.expires_at));
  }, [sessions, now]);
  const historySessions = useMemo(
    () => sessions
      .filter((s) => !(s.status === 'ACTIVE' && new Date(s.expires_at) > now))
      .sort((a, b) => new Date(b.started_at || b.expires_at) - new Date(a.started_at || a.expires_at))
      .slice(0, 8),
    [sessions, now]
  );

  const activeSession = selectedSession;

  return (
    <div className="space-y-4">
      <SectionHeader
        area="attendance"
        icon={ClipboardCheck}
        title="Attendance"
        subtitle="Take a register with a projected code, or hand stations to students. Records save as people scan."
        crumb={[{ label: 'FET Platform' }, { label: 'Attendance' }]}
        actions={(
          <button type="button" onClick={() => setShowCreateSession(true)} className="fet-btn-primary">
            <Plus size={15} /> Start session
          </button>
        )}
      />

      {flash ? <Callout tone="ok" icon={CheckCircle2}>{flash}</Callout> : null}

      {/* Live sessions */}
      {displaySessions.length === 0 ? (
        <Card accent="attendance">
          <EmptyState
            icon={Calendar}
            title="No session is running"
            subtitle="Start a session to open a register. Project a code on the wall, or let students act as stations."
            action={(
              <button type="button" onClick={() => setShowCreateSession(true)} className="fet-btn-primary">
                <Plus size={15} /> Start session
              </button>
            )}
          />
        </Card>
      ) : null}

      <div className="space-y-4">
        {displaySessions.map((session) => {
          const present = session.present ?? session.total_present ?? 0;
          const eligible = session.total_eligible ?? '—';
          const pct = eligible === '—' || eligible === 0 ? 0 : Math.round((present / eligible) * 100);
          const left = secondsLeft(new Date(session.expires_at).getTime(), now);
          return (
            <div key={session.id} className="ui-live">
              <div className="ui-live-top">
                <div className="flex flex-wrap items-start justify-between gap-3">
                  <div className="min-w-0">
                    <div className="mb-1 flex flex-wrap items-center gap-2">
                      <span className="text-[13.5px] font-semibold text-text-primary">{session.course_code}</span>
                      <Pill tone="ok" dot>Live</Pill>
                      <Tag>{session.mode === 'PROJECTOR' ? 'Projected code' : 'Student stations'}</Tag>
                    </div>
                    <p className="text-[12px] text-text-secondary">{session.class_name}</p>
                    {session.expected_headcount ? (
                      <p className="mt-1 text-[11.5px] text-text-secondary">
                        Headcount target {session.expected_headcount}
                        {session.headcount_remaining != null ? `, ${session.headcount_remaining} remaining` : ''}
                      </p>
                    ) : null}
                  </div>
                  <div className="text-right">
                    <Eyebrow>Window closes in</Eyebrow>
                    <div className="ui-clock">{Math.floor(left / 60)}:{String(left % 60).padStart(2, '0')}</div>
                  </div>
                </div>
              </div>

              <div className="ui-card-body">
                <div className="mb-4 grid grid-cols-2 gap-4 md:grid-cols-4">
                  {[
                    { label: 'Present', value: present },
                    { label: 'Eligible', value: eligible },
                    { label: 'Rate', value: `${pct}%` },
                    { label: 'Stations', value: checkpoints[session.id]?.length || 0 },
                  ].map((f) => (
                    <div key={f.label}>
                      <Eyebrow>{f.label}</Eyebrow>
                      <div className="ui-stat-value" style={{ fontSize: 22 }}>{f.value}</div>
                    </div>
                  ))}
                </div>
                <div className="flex flex-wrap items-center gap-2">
                  {session.mode !== 'STATIONS' ? (
                    <button
                      type="button"
                      onClick={() => { setSelectedSession(session); setShowProjector(true); }}
                      className="fet-btn-primary"
                    >
                      <Monitor size={15} /> Project code
                    </button>
                  ) : (
                    <span className="fet-btn-secondary" aria-hidden="true">
                      <Users size={15} /> Stations mode
                    </span>
                  )}
                  <button
                    type="button"
                    onClick={() => { setSelectedSession(session); loadRecords(session); loadCheckpoints(session.id); }}
                    className="fet-btn-secondary"
                  >
                    <Eye size={15} /> View register
                  </button>
                  <div className="flex-1" />
                  <button
                    type="button"
                    onClick={() => handleCloseSession(session)}
                    className="fet-btn-danger"
                  >
                    <Square size={14} /> Close session
                  </button>
                </div>
              </div>

              {session.mode === 'STATIONS' ? (
                <div style={{ padding: '0 16px 16px' }}>
                  <Card accent="attendance">
                    <CardHead title="Student stations" square="att">
                      <button
                        type="button"
                        onClick={() => handleAutoSelect(session)}
                        disabled={autoSelecting}
                        className="fet-btn-secondary"
                        style={{ padding: '6px 11px', fontSize: 12.5 }}
                      >
                        {autoSelecting
                          ? <><Loader2 size={14} className="animate-spin" /> Selecting...</>
                          : <><RefreshCw size={14} /> Auto select</>}
                      </button>
                      <button type="button" onClick={() => openStationPicker(session)} className="fet-btn-primary" style={{ padding: '6px 11px', fontSize: 12.5 }}>
                        <UserCheck size={14} /> Select students
                      </button>
                    </CardHead>
                    <CardBody>
                      {rosterLoading && stationPickerFor === session.id ? (
                        <div className="flex items-center justify-center gap-2 py-4 text-sm text-text-secondary">
                          <Loader2 size={15} className="animate-spin" /> Loading roster...
                        </div>
                      ) : rosterError && stationPickerFor === session.id ? (
                        <Callout tone="wn" icon={AlertCircle}>
                          <div className="flex flex-col items-center gap-2">
                            <span>{rosterError}</span>
                            <button type="button" onClick={() => openStationPicker(session)} className="fet-btn-secondary" style={{ padding: '6px 11px', fontSize: 12.5 }}>
                              <RefreshCw size={14} /> Try again
                            </button>
                          </div>
                        </Callout>
                      ) : stationPickerFor === session.id ? (
                        <StationPickerBody
                          roster={roster}
                          picked={pickedStations}
                          onToggle={toggleStation}
                          onSave={() => saveStations(session)}
                          saving={savingStations}
                        />
                      ) : (checkpoints[session.id]?.length || 0) === 0 ? (
                        <p className="text-[12.5px] text-text-secondary">
                          No stations picked yet. Choose the students who have their phone out and are ready
                          to show a code.
                        </p>
                      ) : (
                        <div className="flex flex-wrap items-center gap-2">
                          {checkpoints[session.id].map((c) => (
                            <span key={c.id} className="ui-pill pill-in">
                              {c.checkpoint_number} &nbsp;{c.student_name}
                              <button
                                type="button"
                                onClick={() => removeStation(session, c)}
                                disabled={removingStation === c.id}
                                className="ml-0.5 rounded-full hover:text-danger"
                                title={`Remove ${c.student_name} as a station`}
                                aria-label={`Remove ${c.student_name} as a station`}
                              >
                                {removingStation === c.id
                                  ? <Loader2 size={11} className="animate-spin" />
                                  : <X size={11} />}
                              </button>
                            </span>
                          ))}
                        </div>
                      )}
                    </CardBody>
                  </Card>
                </div>
              ) : null}
            </div>
          );
        })}
      </div>

      {/* History */}
      {historySessions.length > 0 && (
        <div className="fet-card overflow-hidden">
          <div className="p-6 border-b border-border-default">
            <h3 className="text-lg font-semibold text-text-primary">History</h3>
            <p className="text-sm text-text-secondary">Sessions started in this browser since load. Full history is available on the backend.</p>
          </div>
          <div className="overflow-x-auto">
            <table className="fet-table">
              <thead>
                <tr>
                  <th>Course</th>
                  <th>Class</th>
                  <th>Started</th>
                  <th>Present</th>
                  <th>Status</th>
                </tr>
              </thead>
              <tbody>
                {historySessions.map((session) => (
                  <tr key={session.id}>
                    <td className="font-medium">{session.course_code}</td>
                    <td>{session.class_name}</td>
                    <td>{fmtDate(session.started_at)}</td>
                    <td>{session.present ?? session.total_present ?? 0}</td>
                    <td><span className={getStatusColor(session.status)}>{session.status}</span></td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}

      {/* Create session modal */}
      {showCreateSession && (
        <AttendanceSession user={{ role: 'lecturer' }} onClose={() => setShowCreateSession(false)} onCreated={handleSessionCreated} />
      )}

      {/* Projector overlay with REAL QR */}
      {showProjector && activeSession && (
        <div className="fixed inset-0 bg-[#0a0a1a] z-[100] flex flex-col items-center justify-center p-8">
          <button
            onClick={() => { setShowProjector(false); setProjectorToken(null); setProjectorError(''); }}
            className="absolute top-4 right-4 flex items-center gap-2 px-4 py-2 bg-white/10 text-white rounded-xl hover:bg-white/20"
          >
            <X size={18} /> Exit Projector
          </button>
          <div className="flex items-center gap-2 text-white/60 mb-4">
            <Clock size={16} />
            <span>
              Closes in:{' '}
              <span className="font-bold text-white">
                {Math.max(0, Math.floor((projectorRemaining / 1000) / 60))}:
                {String(Math.max(0, Math.floor((projectorRemaining / 1000) % 60))).padStart(2, '0')}
              </span>
            </span>
            <span className="ml-4 text-white/40">QR refreshes every {projectorExpiresIn}s</span>
            <span className="ml-4">Present: <span className="font-bold">{activeSession.present ?? activeSession.total_present ?? 0}</span></span>
            {activeSession.expected_headcount ? (
              <span className="ml-4">Headcount remaining: <span className="font-bold">{activeSession.headcount_remaining ?? 0}</span></span>
            ) : null}
          </div>
          <div className="bg-white rounded-3xl p-10 shadow-2xl">
            {projectorToken ? (
              <QRCodeDisplay value={projectorToken} size={360} />
            ) : projectorError ? (
              <div className="w-[360px] h-[360px] flex flex-col items-center justify-center gap-3 text-center px-4">
                <AlertCircle size={44} className="text-red-500" />
                <p className="font-semibold text-text-primary">No QR code</p>
                <p className="text-sm text-text-secondary">{projectorError}</p>
                <button
                  onClick={() => { setShowProjector(false); setShowCreateSession(true); }}
                  className="fet-btn-primary mt-2"
                >
                  Start a new session
                </button>
              </div>
            ) : (
              <div className="w-[360px] h-[360px] flex items-center justify-center">
                <Loader2 size={48} className="animate-spin text-[#0F0B3D]" />
              </div>
            )}
          </div>
          <p className="text-white font-mono text-xl mt-6 font-bold tracking-widest break-all max-w-xl text-center">
            {projectorToken || (projectorError ? 'No QR code' : 'Generating QR...')}
          </p>
          <p className="mt-2 text-white/60">
            {projectorStudent ? `Student: ${projectorStudent} | ` : ''}
            {activeSession.course_code} | {activeSession.class_name}
          </p>
        </div>
      )}

      {/* View session modal with records + corrections */}
      {selectedSession && !showProjector && (
        <div className="fixed inset-0 bg-black/50 backdrop-blur-sm flex items-center justify-center z-50 p-4">
          <div className="fet-card bg-white rounded-2xl shadow-modal max-w-4xl w-full max-h-[90vh] overflow-y-auto p-6">
            <div className="flex items-center justify-between mb-4">
              <h3 className="text-xl font-bold text-text-primary">Session Details</h3>
              <div className="flex items-center gap-2">
                {selectedSession.status === 'ACTIVE' && (
                  <button
                    onClick={() => handleCloseSession(selectedSession)}
                    className="flex items-center gap-1 px-3 py-1.5 bg-danger text-white rounded-lg text-xs font-medium hover:bg-red-700"
                  >
                    <Square size={14} /> Close Session
                  </button>
                )}
                <button onClick={() => { setSelectedSession(null); setCorrectingRecord(null); }} className="p-1 hover:bg-page-bg rounded-lg">
                  <X size={18} />
                </button>
              </div>
            </div>

            <div className="grid grid-cols-2 gap-4 mb-4">
              <div><span className="font-semibold">Course:</span> {selectedSession.course_code} - {selectedSession.class_name}</div>
              <div><span className="font-semibold">Started:</span> {fmtDate(selectedSession.started_at)} {fmtTime(selectedSession.started_at)}</div>
              <div><span className="font-semibold">Expires:</span> {fmtTime(selectedSession.expires_at)}</div>
              <div><span className="font-semibold">Status:</span> {selectedSession.status}</div>
            </div>

            <h4 className="font-semibold text-text-primary mb-2">Attendance Records ({records[selectedSession.id]?.length || 0})</h4>
            <div className="overflow-x-auto">
              <table className="fet-table">
                <thead>
                  <tr>
                    <th>Student</th>
                    <th>Email</th>
                    <th>Status</th>
                    <th>Method</th>
                    <th>Time</th>
                    <th>Actions</th>
                  </tr>
                </thead>
                <tbody>
                  {(records[selectedSession.id] || []).map((record) => (
                    <tr key={record.id}>
                      <td className="font-medium">{record.student_name}</td>
                      <td className="text-sm">{record.student_email}</td>
                      <td><span className={getRecordStatusColor(record.status)}>{record.status}</span></td>
                      <td className="text-sm">{record.verification_method}</td>
                      <td className="text-sm">{fmtTime(record.recorded_at)}</td>
                      <td>
                        <div className="flex items-center gap-3">
                          <button
                            onClick={() => {
                              setCorrectingRecord(record);
                              setCorrectionStatus(record.status);
                              setCorrectionReason('');
                            }}
                            className="flex items-center gap-1 text-xs text-primary hover:underline"
                          >
                            <Pencil size={14} /> Correct
                          </button>
                        </div>
                      </td>
                    </tr>
                  ))}
                  {(records[selectedSession.id] || []).length === 0 && (
                    <tr>
                      <td colSpan={6} className="text-center py-8 text-text-secondary">
                        <Loader2 size={20} className="inline animate-spin mr-2" />No records loaded yet
                      </td>
                    </tr>
                  )}
                </tbody>
              </table>
            </div>

            {correctingRecord && (
              <div className="mt-4 p-4 border border-border-default rounded-xl bg-page-bg">
                <h5 className="font-semibold text-text-primary mb-2">
                  Correct attendance for {correctingRecord.student_name}
                </h5>
                <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
                  <div>
                    <label className="fet-label">New Status</label>
                    <select value={correctionStatus} onChange={(e) => setCorrectionStatus(e.target.value)} className="fet-select">
                      <option value="PRESENT">Present</option>
                      <option value="LATE">Late</option>
                      <option value="ABSENT">Absent</option>
                      <option value="EXCUSED">Excused</option>
                    </select>
                  </div>
                  <div>
                    <label className="fet-label">Reason</label>
                    <textarea
                      value={correctionReason}
                      onChange={(e) => setCorrectionReason(e.target.value)}
                      className="fet-input resize-none"
                      rows={3}
                      maxLength={2000}
                      placeholder="Explain why this record is being corrected"
                    />
                  </div>
                </div>
                <div className="mt-3 flex gap-2">
                  <button
                    onClick={() => handleCorrect(correctingRecord)}
                    className="fet-btn-primary"
                    disabled={!correctionReason.trim() || correctionStatus === correctingRecord.status}
                  >
                    Save Correction
                  </button>
                  <button onClick={() => setCorrectingRecord(null)} className="fet-btn-secondary">
                    Cancel
                  </button>
                </div>
              </div>
            )}
          </div>
        </div>
      )}
    </div>
  );
};

/* ------------------------------- ENTRY -------------------------------- */
const AttendanceDashboard = ({ user }) => {
  if (!isLecturerRole(user)) {
    return <StudentAttendance user={user} />;
  }
  return <LecturerAttendance user={user} />;
};

export default AttendanceDashboard;
