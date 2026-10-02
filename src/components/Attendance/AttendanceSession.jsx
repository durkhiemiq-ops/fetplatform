import React, { useState } from 'react';
import { useAppContext } from '../../context/AppContext';
import { X, Users, QrCode } from 'lucide-react';
import { getClasses } from '../../api/academic';

/**
 * AttendanceSession — create an attendance session for one of the lecturer's
 * class sessions. The backend binds attendance to a ClassSession (row), and
 * eligibility + strict per-student checkpointing happens on the server after
 * launch (`selectCheckpoints` -> `issueCheckpointToken`).
 */
const AttendanceSession = ({ user, onClose, onCreated }) => {
  const { addAttendanceSession, courses } = useAppContext();
  const [courseCode, setCourseCode] = useState('');
  const [classSessionId, setClassSessionId] = useState('');
  const [durationSeconds, setDurationSeconds] = useState(60);
  const [error, setError] = useState('');
  const [busy, setBusy] = useState(false);
  const { attendanceSessions } = useAppContext();

  // Only class sessions for the courses this lecturer teaches
  const [classSessions, setClassSessions] = useState([]);

  React.useEffect(() => {
    // Load accessible class sessions from the API.
    (async () => {
      try {
        const classes = await getClasses();
        // class sessions reference course ids; resolve display from loaded courses
        const myClasses = classes.filter(() => true); // academic list is already context-filtered
        setClassSessions(myClasses);
      } catch (err) {
        setError(err.message || 'Could not load classes.');
      }
    })();
  }, []);

  const classesForCourse = (code) => classSessions.filter((c) => c.course_code === code);

  const handleSubmit = async () => {
    if (!courseCode || !classSessionId) {
      setError('Please select a course and class session');
      return;
    }
    setBusy(true);
    setError('');
    try {
      const session = await addAttendanceSession({
        classSessionId,
        duration_seconds: Math.min(Math.max(parseInt(durationSeconds, 10) || 60, 10), 600),
      });
      onCreated && onCreated(session);
      onClose && onClose();
    } catch (err) {
      setError(err.message || 'Could not start the session.');
    } finally {
      setBusy(false);
    }
  };

  const myCourseCodes = [...new Set(classSessions.map((c) => c.course_code))];

  return (
    <div className="fixed inset-0 bg-black/50 backdrop-blur-sm flex items-center justify-center z-50 p-4">
      <div className="fet-card bg-white rounded-2xl shadow-modal max-w-xl w-full p-6">
        <div className="flex items-center justify-between mb-6">
          <h3 className="text-xl font-bold text-text-primary">Create Attendance Session</h3>
          <button onClick={onClose} className="p-1 hover:bg-page-bg rounded-lg" aria-label="Close">
            <X size={22} className="text-text-secondary" />
          </button>
        </div>

        {error && (
          <div className="bg-red-50 border border-red-200 text-danger px-4 py-3 rounded-xl text-sm mb-4">
            {error}
          </div>
        )}

        <div className="space-y-4">
          <div>
            <label className="fet-label">Course *</label>
            <select
              value={courseCode}
              onChange={(e) => { setCourseCode(e.target.value); setClassSessionId(''); }}
              className="fet-select"
            >
              <option value="">Select course</option>
              {myCourseCodes.map((c) => (
                <option key={c} value={c}>{c}</option>
              ))}
            </select>
          </div>

          {courseCode && (
            <div>
              <label className="fet-label">Class session *</label>
              <select
                value={classSessionId}
                onChange={(e) => setClassSessionId(e.target.value)}
                className="fet-select"
              >
                <option value="">Select class session</option>
                {classesForCourse(courseCode).map((s) => (
                  <option key={s.id} value={s.id}>
                    {s.course_code} — {new Date(s.starts_at).toLocaleString()}
                  </option>
                ))}
              </select>
            </div>
          )}

          <div>
            <label className="fet-label">Session duration (seconds, 10–600)</label>
            <input
              type="number"
              min={10}
              max={600}
              value={durationSeconds}
              onChange={(e) => setDurationSeconds(e.target.value)}
              className="fet-input"
            />
          </div>

          <div className="p-4 bg-page-bg rounded-xl text-sm text-text-secondary">
            <p className="font-medium text-text-primary mb-1">How attendance works</p>
            <p>After launching, you'll select which students become checkpoints, then project each
            checkpoint's rotating QR (10-second TTL, single-use, student-bound) for that student to scan.</p>
          </div>

          <button
            onClick={handleSubmit}
            disabled={busy || !courseCode || !classSessionId}
            className="w-full fet-btn-primary disabled:opacity-60"
          >
            {busy ? 'Launching…' : 'Launch Attendance'}
          </button>
        </div>
      </div>
    </div>
  );
};

export default AttendanceSession;
