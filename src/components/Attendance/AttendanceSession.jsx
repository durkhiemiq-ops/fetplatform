import React, { useState, useEffect } from 'react';
import { createPortal } from 'react-dom';
import attendanceApi from '../../lib/attendance';
import { X, Users, QrCode, ChevronRight, Loader2, AlertCircle } from 'lucide-react';

const DAYS = ['MONDAY', 'TUESDAY', 'WEDNESDAY', 'THURSDAY', 'FRIDAY', 'SATURDAY', 'SUNDAY'];

const AttendanceSession = ({ onClose, onCreated }) => {
  const [step, setStep] = useState(1);
  const [courses, setCourses] = useState([]);
  const [loadingCourses, setLoadingCourses] = useState(true);
  const [starting, setStarting] = useState(false);
  const [error, setError] = useState('');
  const [formData, setFormData] = useState({
    offeringId: '',
    scheduleId: '',
    mode: 'PROJECTOR',
    windowMinutes: 5,
    expectedHeadcount: '',
  });

  useEffect(() => {
    (async () => {
      try {
        const data = await attendanceApi.lecturerCourses();
        setCourses(Array.isArray(data) ? data : []);
      } catch (err) {
        setError(err.response?.data?.error?.message || 'Could not load your courses.');
      } finally {
        setLoadingCourses(false);
      }
    })();
  }, []);

  const offering = courses.find((c) => c.offering_id === formData.offeringId);
  const schedule = offering?.schedules?.find((s) => String(s.id) === String(formData.scheduleId));

  const fmtTime = (t) => (t ? String(t).slice(0, 5) : '');

  const handleSubmit = async () => {
    if (!formData.offeringId) {
      setError('Please select a course.');
      return;
    }
    setStarting(true);
    setError('');
    try {
      const payload = {
        offering_id: formData.offeringId,
        mode: formData.mode,
        // How long attendance stays OPEN (minutes chosen by the lecturer).
        // The QR token TTL is a separate, server-side security setting.
        duration_seconds: Math.max(60, Math.round(Number(formData.windowMinutes || 5) * 60)),
      };
      if (formData.scheduleId) payload.schedule_id = formData.scheduleId;
      if (formData.expectedHeadcount) payload.expected_headcount = Number(formData.expectedHeadcount);

      const session = await attendanceApi.startFlex(payload);

      if (onCreated) onCreated(session);
      if (onClose) onClose();
    } catch (err) {
      setError(err.response?.data?.error?.message || 'Could not start the attendance session.');
    } finally {
      setStarting(false);
    }
  };

  return (
    <div className="fixed inset-0 bg-black/50 backdrop-blur-sm flex items-center justify-center z-[120] p-4">
      <div className="fet-card bg-white rounded-2xl shadow-modal max-w-2xl w-full max-h-[90vh] overflow-y-auto">
        <div className="flex items-center justify-between p-6 border-b border-border-default">
          <h3 className="text-xl font-bold text-text-primary">Start Attendance Session</h3>
          <button onClick={onClose} className="p-1 hover:bg-page-bg rounded-lg">
            <X size={24} className="text-text-secondary" />
          </button>
        </div>

        <div className="flex items-center justify-center gap-4 p-4 bg-page-bg border-b border-border-default">
          {[1, 2].map((s) => (
            <div key={s} className="flex items-center gap-2">
              <div className={`w-8 h-8 rounded-full flex items-center justify-center text-sm font-semibold ${
                step >= s ? 'bg-primary text-white' : 'bg-page-bg text-text-secondary'
              }`}>
                {s}
              </div>
              {s < 2 && <ChevronRight size={16} className="text-text-secondary" />}
            </div>
          ))}
        </div>

        <div className="p-6">
          {error && (
            <div className="bg-red-50 border border-red-200 text-danger px-4 py-3 rounded-xl text-sm mb-4 flex items-center gap-2">
              <AlertCircle size={16} />
              {error}
            </div>
          )}

          {/* Step 1: Course + Mode */}
          {step === 1 && (
            <div className="space-y-4">
              <div>
                <label className="fet-label">Course *</label>
                {loadingCourses ? (
                  <div className="flex items-center gap-2 text-text-secondary text-sm py-2">
                    <Loader2 size={16} className="animate-spin" /> Loading your courses...
                  </div>
                ) : (
                  <select
                    value={formData.offeringId}
                    onChange={(e) => setFormData((prev) => ({ ...prev, offeringId: e.target.value, scheduleId: '' }))}
                    className="fet-select"
                  >
                    <option value="">Select Course</option>
                    {courses.map((c) => (
                      <option key={c.offering_id} value={c.offering_id}>
                        {c.course_code} - {c.course_title} ({c.enrolled_students} enrolled)
                      </option>
                    ))}
                  </select>
                )}
              </div>

              {offering && offering.schedules?.length > 0 && (
                <div>
                  <label className="fet-label">Timetable slot (optional)</label>
                  <select
                    value={formData.scheduleId}
                    onChange={(e) => setFormData((prev) => ({ ...prev, scheduleId: e.target.value }))}
                    className="fet-select"
                  >
                    <option value="">Now (custom / unscheduled)</option>
                    {offering.schedules.map((s) => (
                      <option key={s.id} value={s.id}>
                        {DAYS.includes(s.day_of_week) ? s.day_of_week : ''} {fmtTime(s.start_time)}–{fmtTime(s.end_time)} {s.location ? `· ${s.location}` : ''}
                      </option>
                    ))}
                  </select>
                </div>
              )}

              <div>
                <label className="fet-label">Attendance Mode</label>
                <div className="grid grid-cols-2 gap-3">
                  <button
                    type="button"
                    onClick={() => setFormData((prev) => ({ ...prev, mode: 'STATIONS' }))}
                    className={`p-4 rounded-xl border-2 transition-colors text-center ${
                      formData.mode === 'STATIONS'
                        ? 'border-primary bg-primary/10 text-primary'
                        : 'border-border-default hover:border-primary'
                    }`}
                  >
                    <Users size={24} className="mx-auto mb-1" />
                    <p className="text-sm font-medium">Student Stations</p>
                    <p className="text-xs text-text-secondary">Multiple student QR points</p>
                  </button>
                  <button
                    type="button"
                    onClick={() => setFormData((prev) => ({ ...prev, mode: 'PROJECTOR' }))}
                    className={`p-4 rounded-xl border-2 transition-colors text-center ${
                      formData.mode === 'PROJECTOR'
                        ? 'border-primary bg-primary/10 text-primary'
                        : 'border-border-default hover:border-primary'
                    }`}
                  >
                    <QrCode size={24} className="mx-auto mb-1" />
                    <p className="text-sm font-medium">Projected QR</p>
                    <p className="text-xs text-text-secondary">One QR on the screen</p>
                  </button>
                </div>
              </div>

              <button onClick={() => setStep(2)} className="w-full fet-btn-primary">
                Continue →
              </button>
            </div>
          )}

          {/* Step 2: Options + Launch */}
          {step === 2 && (
            <div className="space-y-4">
              <div className="p-4 bg-page-bg rounded-xl">
                <p className="font-medium text-text-primary">{offering.course_code} - {offering.course_title}</p>
                <p className="text-sm text-text-secondary">
                  {formData.mode === 'STATIONS' ? 'Student Stations mode' : 'Projected QR mode'}
                  {schedule ? ` · scheduled ${fmtTime(schedule.start_time)}–${fmtTime(schedule.end_time)}` : ' · unscheduled / now'}
                </p>
                <p className="text-sm text-text-secondary">{offering.enrolled_students} students enrolled</p>
              </div>

              <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
                <div>
                  <label className="fet-label">Attendance window (minutes)</label>
                  <input
                    type="number"
                    min={1}
                    max={10}
                    value={formData.windowMinutes}
                    onChange={(e) => setFormData((prev) => ({ ...prev, windowMinutes: Number(e.target.value) }))}
                    className="fet-input"
                  />
                  <p className="text-xs text-text-secondary mt-1">
                    How long attendance stays open for students to scan.
                  </p>
                  <p className="text-[11px] text-text-secondary mt-1">
                    The QR code itself refreshes every 10s for security &mdash; separate, and automatic.
                  </p>
                </div>
                <div>
                  <label className="fet-label">Expected headcount (optional)</label>
                  <input
                    type="number"
                    min={1}
                    value={formData.expectedHeadcount}
                    onChange={(e) => setFormData((prev) => ({ ...prev, expectedHeadcount: e.target.value }))}
                    placeholder="Auto-close after N check-ins"
                    className="fet-input"
                  />
                  <p className="text-xs text-text-secondary mt-1">
                    Closes early once this many students have checked in.
                  </p>
                </div>
              </div>

              {formData.mode === 'STATIONS' && (
                <div className="p-4 bg-page-bg rounded-xl">
                  <p className="text-sm font-medium text-text-primary">Auto stations unlock after people check in</p>
                  <p className="text-xs text-text-secondary mt-1">
                    Stations are picked from students who are already verified present in this session. Once enough
                    students have scanned, use the <strong>“Auto-select stations”</strong> button on the session screen
                    to let the system pick them — it never guesses about who is actually in the room.
                  </p>
                </div>
              )}

              {formData.mode === 'PROJECTOR' && (
                <div className="p-6 bg-page-bg rounded-xl text-center">
                  <QrCode size={48} className="mx-auto text-primary mb-2" />
                  <h4 className="text-lg font-semibold text-text-primary">Projected QR Mode</h4>
                  <p className="text-sm text-text-secondary">One rotating QR will be shown on your screen — 200 students can scan it in a few minutes.</p>
                </div>
              )}

              <div className="flex gap-3">
                <button onClick={() => setStep(1)} className="flex-1 fet-btn-secondary" disabled={starting}>
                  Back
                </button>
                <button
                  onClick={handleSubmit}
                  disabled={starting}
                  className="flex-1 fet-btn-success flex items-center justify-center gap-2"
                >
                  {starting && <Loader2 size={18} className="animate-spin" />}
                  Launch Attendance
                </button>
              </div>
            </div>
          )}
        </div>
      </div>
    </div>
  );
};

const AttendanceSessionModal = (props) =>
  createPortal(<AttendanceSession {...props} />, document.body);

export default AttendanceSessionModal;