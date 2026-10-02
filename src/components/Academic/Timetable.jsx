import React, { useState, useEffect, useCallback } from 'react';
import { CalendarClock, Plus, Trash2 } from 'lucide-react';
import {
  SectionHeader, Card, CardBody, CardHead, Pill, Callout, EmptyState, Eyebrow,
} from '../UI';
import { academicsApi, DAY_NAMES } from '../../lib/academics';
import { errorMessage } from '../../lib/enrollment';
import { learningApi } from '../../lib/learning';
import { useSession } from '../../context/SessionContext';
import { formatClock } from '../../lib/format';

const DAYS = ['MONDAY', 'TUESDAY', 'WEDNESDAY', 'THURSDAY', 'FRIDAY', 'SATURDAY', 'SUNDAY'];
const CLASS_TYPES = ['LECTURE', 'LAB', 'TUTORIAL', 'SEMINAR', 'WORKSHOP'];

const emptySlot = { day_of_week: 'MONDAY', start_time: '08:00', end_time: '09:00', location: '', class_type: 'LECTURE' };

const Timetable = () => {
  const [offerings, setOfferings] = useState([]);
  const [offeringId, setOfferingId] = useState('');
  const [slots, setSlots] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [showForm, setShowForm] = useState(false);
  const [form, setForm] = useState(emptySlot);
  const [busy, setBusy] = useState(false);
  const { role: sessionRole, isStaff: sessionIsStaff } = useSession();
  const [isStaff, setIsStaff] = useState(sessionIsStaff);

  useEffect(() => {
    setIsStaff(sessionIsStaff);
  }, [sessionIsStaff]);

  // Offerings this user is allowed to see a timetable for.
  useEffect(() => {
    (async () => {
      setLoading(true);
      setError('');
      try {
        const courses = await learningApi.getMyCourses(sessionRole);
        setOfferings(courses || []);
        if (courses?.length) setOfferingId((prev) => prev || courses[0].offering_id);
      } catch (err) {
        setError(errorMessage(err, 'Could not load your courses.'));
      } finally {
        setLoading(false);
      }
    })();
  }, [sessionRole]);

  const loadSlots = useCallback(async (id) => {
    if (!id) { setSlots([]); return; }
    setError('');
    try {
      setSlots((await academicsApi.schedules(id)) || []);
    } catch (err) {
      setError(errorMessage(err, 'Could not load the timetable.'));
    }
  }, []);

  useEffect(() => { loadSlots(offeringId); }, [offeringId, loadSlots]);

  const addSlot = async (e) => {
    e.preventDefault();
    setBusy(true);
    setError('');
    try {
      await academicsApi.createSchedule(offeringId, {
        day_of_week: form.day_of_week,
        start_time: form.start_time,
        end_time: form.end_time,
        location: form.location.trim(),
        class_type: form.class_type,
      });
      setForm(emptySlot);
      setShowForm(false);
      await loadSlots(offeringId);
    } catch (err) {
      setError(errorMessage(err, 'Could not add that slot.'));
    } finally {
      setBusy(false);
    }
  };

  const removeSlot = async (slotId) => {
    setError('');
    try {
      await academicsApi.deleteSchedule(slotId);
      await loadSlots(offeringId);
    } catch (err) {
      setError(errorMessage(err, 'Could not remove that slot.'));
    }
  };

  const byDay = DAYS.map((d) => ({
    day: d,
    items: slots.filter((s) => s.day_of_week === d).sort((a, b) => a.start_time.localeCompare(b.start_time)),
  })).filter((g) => g.items.length > 0);

  return (
    <div className="space-y-5">
      <SectionHeader
        area="classrooms"
        icon={CalendarClock}
        title="Timetable"
        subtitle="The weekly pattern of classes. Attendance sessions are checked against this."
        actions={isStaff && offeringId ? (
          <button type="button" onClick={() => setShowForm((v) => !v)} className="fet-btn-primary">
            <Plus size={14} /> {showForm ? 'Cancel' : 'Add slot'}
          </button>
        ) : null}
      />

      {error ? <Callout tone="bad">{error}</Callout> : null}

      <Card accent="classrooms">
        <CardHead title="Course" square="classrooms" />
        <CardBody>
          {loading ? (
            <p className="text-text-secondary text-[13px] py-4 text-center">Loading courses...</p>
          ) : offerings.length === 0 ? (
            <EmptyState icon={CalendarClock} title="No courses" subtitle="You are not attached to any course offering yet." />
          ) : (
            <select
              className="fet-select"
              value={offeringId}
              onChange={(e) => setOfferingId(e.target.value)}
            >
              {offerings.map((c) => (
                <option key={c.offering_id} value={c.offering_id}>
                  {c.course_code} — {c.course_title}
                </option>
              ))}
            </select>
          )}
        </CardBody>
      </Card>

      {showForm && offeringId ? (
        <Card accent="classrooms">
          <CardHead title="New weekly slot" square="classrooms" />
          <CardBody>
            <form onSubmit={addSlot} className="space-y-3">
              <div className="grid sm:grid-cols-2 gap-3">
                <div>
                  <label className="fet-label">Day</label>
                  <select
                    className="fet-select"
                    value={form.day_of_week}
                    onChange={(e) => setForm({ ...form, day_of_week: e.target.value })}
                  >
                    {DAYS.map((d, i) => (
                      <option key={d} value={d}>{DAY_NAMES[i]}</option>
                    ))}
                  </select>
                </div>
                <div>
                  <label className="fet-label">Type</label>
                  <select
                    className="fet-select"
                    value={form.class_type}
                    onChange={(e) => setForm({ ...form, class_type: e.target.value })}
                  >
                    {CLASS_TYPES.map((t) => <option key={t} value={t}>{t.toLowerCase()}</option>)}
                  </select>
                </div>
              </div>
              <div className="grid sm:grid-cols-2 gap-3">
                <div>
                  <label className="fet-label">Starts</label>
                  <input
                    type="time"
                    className="fet-input"
                    value={form.start_time}
                    onChange={(e) => setForm({ ...form, start_time: e.target.value })}
                    required
                  />
                </div>
                <div>
                  <label className="fet-label">Ends</label>
                  <input
                    type="time"
                    className="fet-input"
                    value={form.end_time}
                    onChange={(e) => setForm({ ...form, end_time: e.target.value })}
                    required
                  />
                </div>
              </div>
              <div>
                <label className="fet-label">Location</label>
                <input
                  className="fet-input"
                  value={form.location}
                  onChange={(e) => setForm({ ...form, location: e.target.value })}
                  placeholder="Room 204"
                />
              </div>
              <div className="flex justify-end">
                <button type="submit" className="fet-btn-primary" disabled={busy}>
                  {busy ? 'Adding...' : 'Add to timetable'}
                </button>
              </div>
            </form>
          </CardBody>
        </Card>
      ) : null}

      {byDay.length === 0 ? (
        <Card accent="classrooms">
          <CardBody>
            <EmptyState
              icon={CalendarClock}
              title="No weekly slots"
              subtitle={isStaff ? 'Add the first slot to build this timetable.' : 'The lecturer has not published a timetable for this course.'}
            />
          </CardBody>
        </Card>
      ) : (
        <div className="grid gap-3 md:grid-cols-2">
          {byDay.map(({ day, items }) => (
            <Card key={day} accent="classrooms">
              <CardHead title={DAY_NAMES[DAYS.indexOf(day)]} square="classrooms">
                <Pill tone="mute">{items.length}</Pill>
              </CardHead>
              <CardBody>
                <ul className="space-y-2">
                  {items.map((s) => (
                    <li key={s.id} className="ui-li flex items-center gap-3">
                      <div className="min-w-0 flex-1">
                        <p className="text-[13px] text-text-primary">
                          {formatClock(s.start_time)} – {formatClock(s.end_time)}
                        </p>
                        <p className="text-[11.5px] text-text-tertiary mt-0.5">
                          <Eyebrow>{s.class_type}</Eyebrow>
                          {s.location ? ` • ${s.location}` : ''}
                        </p>
                      </div>
                      {isStaff ? (
                        <button
                          type="button"
                          onClick={() => removeSlot(s.id)}
                          className="text-text-tertiary hover:text-danger shrink-0"
                          aria-label="Remove slot"
                        >
                          <Trash2 size={15} />
                        </button>
                      ) : null}
                    </li>
                  ))}
                </ul>
              </CardBody>
            </Card>
          ))}
        </div>
      )}
    </div>
  );
};

export default Timetable;
