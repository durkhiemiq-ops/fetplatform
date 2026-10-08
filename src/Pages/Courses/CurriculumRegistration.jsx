import React, { useState, useEffect, useCallback } from 'react';
import { GraduationCap, Check, Info, CalendarClock } from 'lucide-react';
import { useNavigate } from 'react-router-dom';
import { SectionHeader, Card, CardBody, CardHead, CardFoot, Pill, Callout, EmptyState, Eyebrow } from '../../components/UI';
import { curriculumApi } from '../../lib/curriculum';
import { errorMessage } from '../../lib/enrollment';
import { formatDate } from '../../lib/format';

/**
 * Curriculum registration: the server-owned counterpart to the legacy
 * offering-picker registration page.
 *
 * Flow:
 *   registration state
 *   -> specialization required? (server answers from programme configuration)
 *   -> valid choices (server-provided; never hardcoded, never localStorage)
 *   -> select + submit (at most a specialization id leaves this browser)
 *   -> auto-enrollment result + resulting courses
 *
 * Every academic fact on screen (programme, level, curriculum version,
 * required courses, enrollment state) comes from GET state. The POST carries
 * only the chosen specialization, or nothing at all.
 */
const CurriculumRegistration = () => {
  const navigate = useNavigate();
  const [state, setState] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [blocked, setBlocked] = useState(null);
  const [picked, setPicked] = useState('');
  const [busy, setBusy] = useState(false);
  const [notice, setNotice] = useState('');

  const load = useCallback(async () => {
    setLoading(true);
    setError('');
    setBlocked(null);
    try {
      const s = await curriculumApi.state();
      setState(s);
      // Preselect the pinned specialization so resubmission is explicit.
      setPicked(s?.specialization || '');
    } catch (err) {
      const code = err?.response?.data?.error?.code;
      if (code === 'NO_ACTIVE_SEMESTER' || code === 'INCOMPLETE_ACADEMIC_PROFILE') {
        setBlocked({ code, message: err?.response?.data?.error?.message || 'Your academic profile is incomplete.' });
      } else {
        setError(errorMessage(err, 'Could not load your registration state.'));
      }
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { load(); }, [load]);

  const complete = async () => {
    setBusy(true);
    setError('');
    setNotice('');
    try {
      const res = await curriculumApi.complete(
        state?.specialization_required && !state?.specialization ? picked : undefined,
      );
      const created = res?.created_enrollments?.length ?? 0;
      setNotice(
        created > 0
          ? `Registration complete. ${created} course(s) enrolled automatically.`
          : 'Registration already complete. No duplicate enrollments were created.',
      );
      setState(res);
      setPicked(res?.specialization || '');
    } catch (err) {
      setError(errorMessage(err, 'Registration failed.'));
    } finally {
      setBusy(false);
    }
  };

  const required = state?.required_offerings || [];
  const enrolled = required.filter((r) => r.is_enrolled);
  const pending = required.filter((r) => !r.is_enrolled);
  const needsChoice = Boolean(state?.specialization_required && !state?.specialization);
  const canSubmit = !state?.completed && (!needsChoice || picked);

  return (
    <div className="space-y-5">
      <SectionHeader
        area="classrooms"
        icon={GraduationCap}
        title="Curriculum registration"
        subtitle="Your programme's required courses, resolved by the institution curriculum — not picked by hand."
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
          <span className="block mt-1 text-[12px] opacity-80">
            {blocked.code === 'NO_ACTIVE_SEMESTER'
              ? 'An administrator needs to activate a semester before registration opens.'
              : 'An administrator needs to assign your academic programme and cohort first.'}
          </span>
        </Callout>
      ) : null}

      {state ? (
        <Card accent="classrooms">
          <CardHead title={`${state.programme?.name || 'Programme'} • Curriculum v${state.curriculum?.version ?? '?'}`} square="classrooms">
            <Pill tone="mute">Level {state.level}</Pill>
            {state.specialization_required ? <Pill tone="in">Specialization required</Pill> : null}
            {state.completed ? <Pill tone="ok" icon={Check}>Registered</Pill> : null}
          </CardHead>
          <CardBody>
            {state.registration_deadline ? (
              <div className="flex items-center gap-2 text-[12.5px] text-text-secondary mb-4">
                <CalendarClock size={14} />
                Registration closes {formatDate(state.registration_deadline)}
              </div>
            ) : null}

            {needsChoice ? (
              <div className="mb-4">
                <Eyebrow>Choose your specialization</Eyebrow>
                <div className="flex gap-2 flex-wrap mt-2">
                  {state.specializations.map((s) => {
                    const on = picked === s.id;
                    return (
                      <button
                        key={s.id}
                        type="button"
                        onClick={() => { setPicked(s.id); setNotice(''); }}
                        className="ui-li cursor-pointer"
                        style={on ? { borderColor: 'rgb(var(--primary))' } : undefined}
                      >
                        <span className="num text-text-secondary">{s.code}</span> {s.name}
                        {on ? <Pill tone="in" icon={Check}>Selected</Pill> : null}
                      </button>
                    );
                  })}
                </div>
                {state.specializations.length === 0 ? (
                  <p className="text-[12.5px] text-text-secondary mt-2">
                    No active specializations are configured for your programme yet. Contact your administrator.
                  </p>
                ) : null}
              </div>
            ) : state.specialization ? (
              <p className="text-[12.5px] text-text-secondary mb-4">
                Specialization:{' '}
                <span className="font-semibold text-text-primary">
                  {(state.specializations.find((s) => s.id === state.specialization)?.name) || state.specialization}
                </span>{' '}
                (pinned — changes require institutional review)
              </p>
            ) : null}

            {loading ? (
              <p className="text-text-secondary text-[13px] py-6 text-center">Loading required courses...</p>
            ) : required.length === 0 ? (
              <EmptyState
                icon={GraduationCap}
                title="No required courses"
                subtitle="No required curriculum courses are configured for your level and term this semester."
              />
            ) : (
              <ul className="space-y-2">
                {required.map((r) => (
                  <li key={r.offering} className="ui-li flex items-center gap-3">
                    <div className="min-w-0 flex-1">
                      <p className="ui-card-title text-[13px]">
                        <span className="num text-text-secondary">{r.course_code}</span> {r.course_name}
                      </p>
                      <p className="text-[12px] text-text-tertiary mt-0.5">
                        {r.classification === 'PROGRAMME_CORE' ? 'Programme core' : 'Specialization core'}
                      </p>
                    </div>
                    {r.is_enrolled
                      ? <Pill tone="ok" icon={Check}>Enrolled</Pill>
                      : <Pill tone="mute">Pending</Pill>}
                  </li>
                ))}
              </ul>
            )}

            {enrolled.length > 0 && pending.length === 0 && state.completed ? (
              <Callout tone="ok" icon={Check} className="mt-4">
                All {enrolled.length} required course(s) enrolled. You are eligible for their attendance sessions.
              </Callout>
            ) : null}
          </CardBody>
          {!state.completed && required.length > 0 ? (
            <CardFoot>
              <div className="flex items-center justify-between gap-3 flex-wrap">
                <div className="text-[12.5px] text-text-secondary">
                  {enrolled.length} of {required.length} enrolled
                  {needsChoice && !picked ? ' • choose a specialization first' : ''}
                </div>
                <button
                  type="button"
                  onClick={complete}
                  disabled={busy || !canSubmit}
                  className="fet-btn-primary"
                >
                  {busy ? 'Registering...' : 'Complete registration'}
                </button>
              </div>
            </CardFoot>
          ) : null}
        </Card>
      ) : null}
    </div>
  );
};

export default CurriculumRegistration;
