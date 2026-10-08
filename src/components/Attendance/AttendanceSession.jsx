import React, { useEffect, useState } from 'react';
import { createPortal } from 'react-dom';
import { AlertCircle, Loader2, X } from 'lucide-react';

import attendanceApi from '../../lib/attendance';

const AttendanceSession = ({ onClose, onCreated }) => {
  const [courses, setCourses] = useState([]);
  const [offeringId, setOfferingId] = useState('');
  const [windowMinutes, setWindowMinutes] = useState(5);
  const [mode, setMode] = useState('PROJECTOR');
  const [loadingCourses, setLoadingCourses] = useState(true);
  const [starting, setStarting] = useState(false);
  const [error, setError] = useState('');

  useEffect(() => {
    let cancelled = false;
    attendanceApi.lecturerCourses()
      .then((data) => {
        if (!cancelled) setCourses(Array.isArray(data) ? data : []);
      })
      .catch((err) => {
        if (!cancelled) {
          setError(err.response?.data?.error?.message || 'Could not load your courses.');
        }
      })
      .finally(() => {
        if (!cancelled) setLoadingCourses(false);
      });
    return () => { cancelled = true; };
  }, []);

  const selected = courses.find((course) => String(course.id) === String(offeringId));

  const handleSubmit = async (event) => {
    event.preventDefault();
    if (!offeringId) {
      setError('Please select a course.');
      return;
    }

    setStarting(true);
    setError('');
    try {
      const session = await attendanceApi.startFlex({
        offering_id: offeringId,
        duration_seconds: Math.max(
          60,
          Math.min(600, Math.round(Number(windowMinutes || 5) * 60)),
        ),
        mode,
      });
      onCreated?.(session);
      onClose?.();
    } catch (err) {
      setError(err.response?.data?.error?.message || 'Could not start the attendance session.');
    } finally {
      setStarting(false);
    }
  };

  return (
    <div className="fixed inset-0 z-[120] flex items-center justify-center bg-black/50 p-4 backdrop-blur-sm">
      <form onSubmit={handleSubmit} className="fet-card w-full max-w-xl rounded-2xl bg-white shadow-modal">
        <div className="flex items-center justify-between border-b border-border-default p-6">
          <div>
            <h3 className="text-xl font-bold text-text-primary">Start Attendance Session</h3>
            <p className="mt-1 text-sm text-text-secondary">
              Select one assigned course and set the server-enforced attendance window.
            </p>
          </div>
          <button type="button" onClick={onClose} className="rounded-lg p-1 hover:bg-page-bg" aria-label="Close">
            <X size={24} className="text-text-secondary" />
          </button>
        </div>

        <div className="space-y-5 p-6">
          {error ? (
            <div className="flex items-center gap-2 rounded-xl border border-red-200 bg-red-50 px-4 py-3 text-sm text-danger">
              <AlertCircle size={16} />
              {error}
            </div>
          ) : null}

          <div>
            <label className="fet-label" htmlFor="attendance-offering">Course</label>
            {loadingCourses ? (
              <div className="flex items-center gap-2 py-2 text-sm text-text-secondary">
                <Loader2 size={16} className="animate-spin" /> Loading your courses...
              </div>
            ) : (
              <select
                id="attendance-offering"
                value={offeringId}
                onChange={(event) => setOfferingId(event.target.value)}
                className="fet-select"
                required
              >
                <option value="">Select a course...</option>
                {courses.map((course) => (
                  <option key={course.id} value={course.id}>
                    {course.course_code} - {course.course_title}
                  </option>
                ))}
              </select>
            )}
          </div>

          {selected ? (
            <div className="rounded-xl bg-page-bg p-4 text-sm">
              <p className="font-medium text-text-primary">
                {selected.course_code} - {selected.course_title}
              </p>
              <p className="mt-1 text-text-secondary">
                {selected.department_name} · {selected.semester_name}
              </p>
            </div>
          ) : null}

          <fieldset>
            <legend className="fet-label">How students check in</legend>
            <div className="grid grid-cols-1 gap-2 sm:grid-cols-2">
              {[
                {
                  value: 'PROJECTOR',
                  title: 'Projected code',
                  hint: 'One QR on the wall; every enrolled student scans it.',
                },
                {
                  value: 'STATIONS',
                  title: 'Student stations',
                  hint: 'Seed a few phones; classmates scan those instead.',
                },
              ].map((option) => (
                <label
                  key={option.value}
                  className={`flex cursor-pointer items-start gap-2 rounded-xl border p-3 transition-colors ${
                    mode === option.value
                      ? 'border-primary bg-primary/5'
                      : 'border-border-default bg-white hover:border-primary'
                  }`}
                >
                  <input
                    type="radio"
                    name="attendance-mode"
                    value={option.value}
                    checked={mode === option.value}
                    onChange={(event) => setMode(event.target.value)}
                    className="mt-1 accent-primary"
                  />
                  <span className="min-w-0">
                    <span className="block text-sm font-medium text-text-primary">{option.title}</span>
                    <span className="mt-0.5 block text-xs text-text-secondary">{option.hint}</span>
                  </span>
                </label>
              ))}
            </div>
          </fieldset>

          <div>
            <label className="fet-label" htmlFor="attendance-window">Attendance window (minutes)</label>
            <input
              id="attendance-window"
              type="number"
              min="1"
              max="10"
              value={windowMinutes}
              onChange={(event) => setWindowMinutes(event.target.value)}
              className="fet-input"
              required
            />
            <p className="mt-1 text-xs text-text-secondary">
              Each QR code lives 10 seconds and is replaced continuously; this controls only how long the
              session stays open.
            </p>
          </div>

          <div className="flex justify-end gap-3 border-t border-border-default pt-4">
            <button type="button" onClick={onClose} className="fet-btn-secondary" disabled={starting}>
              Cancel
            </button>
            <button type="submit" className="fet-btn-primary" disabled={starting || loadingCourses}>
              {starting ? <Loader2 size={16} className="animate-spin" /> : null}
              Start session
            </button>
          </div>
        </div>
      </form>
    </div>
  );
};

const AttendanceSessionModal = (props) =>
  createPortal(<AttendanceSession {...props} />, document.body);

export default AttendanceSessionModal;
