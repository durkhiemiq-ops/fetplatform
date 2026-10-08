import React, { useState, useEffect, useCallback } from 'react';
import { BookPlus, CalendarClock, Check, Info } from 'lucide-react';
import { useNavigate } from 'react-router-dom';
import { SectionHeader, Card, CardBody, CardHead, CardFoot, Pill, Callout, EmptyState, Eyebrow } from '../../components/UI';
import { enrollmentApi, errorMessage } from '../../lib/enrollment';
import { formatDate } from '../../lib/format';

const RegistrationPage = () => {
  const navigate = useNavigate();
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [blocked, setBlocked] = useState(null);
  const [selected, setSelected] = useState([]);
  const [busy, setBusy] = useState(false);
  const [notice, setNotice] = useState('');

  const load = useCallback(async () => {
    setLoading(true);
    setError('');
    setBlocked(null);
    try {
      setData(await enrollmentApi.availableCourses());
    } catch (err) {
      // These three are setup problems, not transient failures: the user cannot
      // fix them, so say what is missing instead of offering a retry.
      const code = err?.response?.data?.error?.code;
      if (code === 'NO_ACTIVE_SEMESTER' || code === 'INCOMPLETE_PROFILE') {
        setBlocked({
          code,
          message: err?.response?.data?.error?.message || 'Your academic profile is incomplete.',
        });
      } else {
        setError(errorMessage(err, 'Could not load the course list.'));
      }
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { load(); }, [load]);

  const toggle = (id) => {
    setNotice('');
    setSelected((prev) => (prev.includes(id) ? prev.filter((x) => x !== id) : [...prev, id]));
  };

  const register = async () => {
    setBusy(true);
    setError('');
    setNotice('');
    try {
      const res = await enrollmentApi.register(selected);
      const partial = res?.errors?.length
        ? ` ${res.errors.length} could not be registered.`
        : '';
      setNotice(`Registered for ${res?.registered_count ?? 0} course(s).${partial}`);
      setSelected([]);
      await load();
    } catch (err) {
      setError(errorMessage(err, 'Registration failed.'));
    } finally {
      setBusy(false);
    }
  };

  const courses = data?.courses || [];
  const eligible = courses.filter((c) => !c.is_enrolled);
  const done = courses.filter((c) => c.is_enrolled);
  const totalUnits = courses.reduce((sum, c) => sum + (c.credit_units || 0), 0);
  const pickedUnits = courses
    .filter((c) => selected.includes(c.offering_id))
    .reduce((sum, c) => sum + (c.credit_units || 0), 0);

  return (
    <div className="space-y-5">
      <SectionHeader
        area="classrooms"
        icon={BookPlus}
        title="Course registration"
        subtitle="Pick the courses for this semester. Only offerings matching your department and level are listed."
        actions={(
          <button type="button" onClick={() => navigate('/lessons')} className="fet-btn-secondary">
            My courses
          </button>
        )}
      />

      {error ? <Callout tone="bad">{error}</Callout> : null}
      {notice ? <Callout tone="ok">{notice}</Callout> : null}

      {blocked ? (
        <Callout tone="warn" icon={Info}>
          {blocked.message}
          {blocked.code === 'NO_ACTIVE_SEMESTER' ? (
            <span className="block mt-1 text-[12px] opacity-80">
              An administrator needs to activate a semester before registration opens.
            </span>
          ) : (
            <span className="block mt-1 text-[12px] opacity-80">
              Add your department and level on the profile page, then come back.
            </span>
          )}
        </Callout>
      ) : null}

      {data ? (
        <Card accent="classrooms">
          <CardHead title={data.semester || 'Current semester'} square="classrooms">
            <Pill tone="mute">{data.level}</Pill>
            <Pill tone="mute">{data.department}</Pill>
          </CardHead>
          <CardBody>
            {data.registration_deadline ? (
              <div className="flex items-center gap-2 text-[12.5px] text-text-secondary mb-4">
                <CalendarClock size={14} />
                Registration closes {formatDate(data.registration_deadline)}
              </div>
            ) : (
              <Callout tone="warn" className="mb-4">
                No registration deadline is set for this semester.
              </Callout>
            )}

            {loading ? (
              <p className="text-text-secondary text-[13px] py-6 text-center">Loading courses...</p>
            ) : eligible.length === 0 && done.length === 0 ? (
              <EmptyState
                icon={BookPlus}
                title="No courses available"
                subtitle="There are no active offerings for your department and level this semester."
              />
            ) : (
              <ul className="space-y-2">
                {eligible.map((c) => {
                  const on = selected.includes(c.offering_id);
                  return (
                    <li key={c.offering_id}>
                      <label
                        className="ui-li flex items-center gap-3 cursor-pointer"
                        style={on ? { borderColor: 'rgb(var(--primary))' } : undefined}
                      >
                        <input
                          type="checkbox"
                          checked={on}
                          onChange={() => toggle(c.offering_id)}
                          className="w-4 h-4 accent-[rgb(var(--primary))]"
                        />
                        <div className="min-w-0 flex-1">
                          <p className="ui-card-title text-[13px]">
                            <span className="num text-text-secondary">{c.course_code}</span> {c.course_title}
                          </p>
                          <p className="text-[12px] text-text-tertiary mt-0.5">
                            {c.credit_units} units • {c.lecturer_name || 'TBA'}
                          </p>
                        </div>
                        {on ? <Pill tone="in" icon={Check}>Selected</Pill> : null}
                      </label>
                    </li>
                  );
                })}

                {done.length > 0 ? (
                  <li className="pt-3 mt-3 border-t border-border-default">
                    <Eyebrow>Already registered</Eyebrow>
                    <ul className="space-y-1.5">
                      {done.map((c) => (
                        <li key={c.offering_id} className="flex items-center gap-2 text-[13px] text-text-secondary">
                          <Pill tone="ok" icon={Check}>Registered</Pill>
                          <span className="num">{c.course_code}</span> {c.course_title}
                        </li>
                      ))}
                    </ul>
                  </li>
                ) : null}
              </ul>
            )}
          </CardBody>
          {eligible.length > 0 ? (
            <CardFoot>
              <div className="flex items-center justify-between gap-3 flex-wrap">
                <div className="text-[12.5px] text-text-secondary">
                  {selected.length} selected • {pickedUnits} of {totalUnits} units
                </div>
                <button
                  type="button"
                  onClick={register}
                  disabled={busy || selected.length === 0}
                  className="fet-btn-primary"
                >
                  {busy ? 'Registering...' : `Register for ${selected.length || ''} course(s)`}
                </button>
              </div>
            </CardFoot>
          ) : null}
        </Card>
      ) : null}
    </div>
  );
};

export default RegistrationPage;
