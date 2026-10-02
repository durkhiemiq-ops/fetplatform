import React, { useState, useEffect, useCallback } from 'react';
import { useNavigate } from 'react-router-dom';
import { Loader2, Award, BookOpen, ArrowRight, TrendingUp, AlertCircle, Layers } from 'lucide-react';
import attendanceApi from '../../lib/attendance';
import { learningApi } from '../../lib/learning';
import { normalizeRole } from '../../lib/profile';
import AssessmentPanel from './AssessmentPanel';

const StaffAssessments = ({ user }) => {
  const navigate = useNavigate();
  const [courses, setCourses] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [selected, setSelected] = useState('');

  const load = useCallback(async () => {
    setLoading(true);
    setError('');
    try {
      const data = await attendanceApi.lecturerCourses();
      setCourses(Array.isArray(data) ? data : []);
    } catch (err) {
      setError('Could not load your classrooms.');
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { load(); }, [load]);

  if (loading) {
    return (
      <div className="flex flex-col items-center justify-center py-20 gap-3">
        <Loader2 className="h-8 w-8 animate-spin text-primary" />
        <p className="text-sm text-text-secondary">Loading your assessments…</p>
      </div>
    );
  }

  if (courses.length === 0) {
    return (
      <div className="fet-card p-10 text-center">
        <BookOpen size={40} className="mx-auto text-text-secondary opacity-40" />
        <p className="mt-3 font-semibold text-text-primary">No classrooms yet</p>
        <p className="text-sm text-text-secondary mt-1">
          Create a classroom first, then manage its CA and exam marks.
        </p>
        <button onClick={() => navigate('/lessons')} className="fet-btn-primary mt-4">
          Go to Classrooms
        </button>
      </div>
    );
  }

  return (
    <div className="space-y-5">
      {error && (
        <div className="bg-red-50 border border-red-200 text-red-700 px-4 py-3 rounded-xl text-sm">{error}</div>
      )}

      <div className="fet-card p-5">
        <h3 className="text-[15px] font-semibold text-text-primary mb-1">Choose a classroom</h3>
        <p className="text-xs text-text-secondary mb-4">Select the course whose CA / exam marks you want to manage.</p>
        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-3">
          {courses.map((c) => {
            const active = selected === c.offering_id;
            return (
              <button
                key={c.offering_id}
                onClick={() => setSelected(c.offering_id)}
                className={`text-left p-4 rounded-xl border transition-colors ${
                  active ? 'border-primary bg-primary/5' : 'border-border-default hover:border-primary'
                }`}
              >
                <div className="flex items-center justify-between gap-2">
                  <span className="font-semibold text-text-primary text-sm">{c.course_code}</span>
                  {active && <ArrowRight size={15} className="text-primary shrink-0" />}
                </div>
                <p className="text-xs text-text-secondary mt-0.5 line-clamp-2">{c.course_title}</p>
                <p className="text-[11px] text-text-secondary mt-2">
                  {c.assessments_count || 0} assessment{c.assessments_count === 1 ? '' : 's'}
                  {c.ungraded_submissions > 0 && (
                    <span className="ml-2 text-amber-600">{c.ungraded_submissions} to grade</span>
                  )}
                  {c.open_disputes > 0 && (
                    <span className="ml-2 text-red-600">{c.open_disputes} dispute{c.open_disputes === 1 ? '' : 's'}</span>
                  )}
                </p>
              </button>
            );
          })}
        </div>
      </div>

      {selected ? (
        <div>
          <div className="flex items-center justify-between gap-3 mb-3 flex-wrap">
            <h3 className="text-[15px] font-semibold text-text-primary flex items-center gap-2">
              <Award size={16} className="text-primary" />
              {courses.find((c) => c.offering_id === selected)?.course_code} assessments
            </h3>
            <button
              onClick={() => navigate(`/lessons/${selected}`)}
              className="text-xs text-primary font-semibold hover:underline"
            >
              Open classroom →
            </button>
          </div>
          <AssessmentPanel offeringId={selected} user={user} />
        </div>
      ) : (
        <p className="text-sm text-text-secondary text-center py-6">
          Pick a classroom above to see and manage its assessments.
        </p>
      )}
    </div>
  );
};

const StudentAssessments = ({ user }) => {
  const [data, setData] = useState({ assessments: [], groups: [] });
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const res = await learningApi.myAssessments();
      setData({
        assessments: Array.isArray(res?.assessments) ? res.assessments : [],
        groups: Array.isArray(res?.groups) ? res.groups : [],
      });
    } catch (err) {
      setError('Could not load your results.');
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { load(); }, [load]);

  const { assessments: items, groups } = data;
  const totalScore = items.reduce((sum, a) => sum + Number(a.my_mark?.reported_score ?? a.my_mark?.score ?? 0), 0);
  const openDisputes = items.filter((a) => a.my_mark?.dispute_status === 'OPEN').length;

  return (
    <div className="space-y-5">
      <div className="fet-welcome-banner">
        <div className="relative z-10 flex flex-col sm:flex-row items-start sm:items-center justify-between gap-4">
          <div>
            <h2 className="text-[20px] md:text-[22px] font-bold">My Results</h2>
            <p className="text-white/50 text-[13px]">Your released CA and exam marks</p>
            {openDisputes > 0 && (
              <p className="text-white/60 text-[12px] mt-1 flex items-center gap-1.5">
                <AlertCircle size={13} /> {openDisputes} query{openDisputes === 1 ? '' : 'ies'} with your lecturer
              </p>
            )}
          </div>
          <div className="bg-white/10 backdrop-blur-sm rounded-xl px-5 py-3 text-center min-w-[110px] border border-white/10">
            <p className="text-[11px] text-white/50 font-medium uppercase tracking-wider">Total</p>
            <p className="text-[26px] font-bold text-white leading-tight">{totalScore}</p>
          </div>
        </div>
      </div>

      {error && (
        <div className="bg-red-50 border border-red-200 text-red-700 px-4 py-3 rounded-xl text-sm">{error}</div>
      )}

      {loading && (
        <div className="flex justify-center py-12"><Loader2 className="h-7 w-7 animate-spin text-primary" /></div>
      )}

      {!loading && groups.length > 0 && (
        <div className="space-y-3">
          <h3 className="text-[15px] font-semibold text-text-primary flex items-center gap-2">
            <Layers size={16} className="text-primary" /> Combined grades
          </h3>
          {groups.map((g) => {
            const mine = (g.students || [])[0];
            return (
              <div key={g.id} className="fet-card p-5">
                <div className="flex items-center justify-between gap-3 flex-wrap">
                  <div>
                    <h4 className="font-bold text-text-primary">{g.title}</h4>
                    <p className="text-xs text-text-secondary mt-0.5">
                      {g.course_code} · out of {g.maximum_score} · {g.member_count} part{g.member_count === 1 ? '' : 's'}
                    </p>
                  </div>
                  <div className="text-right">
                    <p className="text-xs text-text-secondary">Your grade</p>
                    <p className="text-2xl font-bold text-text-primary">
                      {mine?.total ?? '—'}
                      <span className="text-sm font-normal text-text-secondary"> / {g.maximum_score}</span>
                    </p>
                  </div>
                </div>
                {mine?.breakdown?.length > 0 && (
                  <div className="mt-3 pt-3 border-t border-border-default space-y-1.5">
                    {mine.breakdown.map((b) => (
                      <div key={b.assessment_id} className="flex items-center justify-between gap-3 text-sm">
                        <span className="text-text-secondary">
                          {b.title}
                          {b.raw_score != null && (
                            <span className="text-xs"> (you scored {b.raw_score} / {b.marking_scale})</span>
                          )}
                        </span>
                        <span className={b.points != null ? 'font-semibold text-text-primary' : 'text-text-secondary'}>
                          {b.points != null ? `${b.points} / ${b.contributes_out_of}` : 'not marked'}
                        </span>
                      </div>
                    ))}
                  </div>
                )}
              </div>
            );
          })}
        </div>
      )}

      {!loading && items.length === 0 && groups.length === 0 && (
        <div className="fet-card p-10 text-center">
          <Award size={44} className="mx-auto opacity-40 text-text-secondary" />
          <p className="mt-3 font-semibold text-text-primary">No results released yet</p>
          <p className="text-sm text-text-secondary mt-1">
            Your lecturer will publish your continuous assessment and exam results here.
          </p>
        </div>
      )}

      {!loading && items.map((a) => (
        <div key={a.id} className="fet-card p-5">
          <div className="flex flex-wrap items-start justify-between gap-3">
            <div>
              <div className="flex flex-wrap items-center gap-2">
                <h4 className="font-bold text-text-primary">{a.title}</h4>
                <span className="text-xs font-medium px-2.5 py-1 rounded-full border border-border-default text-text-secondary">
                  {a.category === 'EXAM' ? 'Exam' : 'CA'}
                </span>
                <span className="text-xs font-medium px-2.5 py-1 rounded-full border border-border-default text-text-secondary">
                  {a.course_code}
                </span>
                {a.my_mark?.dispute_status === 'OPEN' && (
                  <span className="text-xs font-medium px-2.5 py-1 rounded-full border bg-amber-50 text-amber-700 border-amber-200">
                    Query raised
                  </span>
                )}
              </div>
              <p className="text-xs text-text-secondary mt-1.5">
                Out of {a.maximum_score}
                {a.is_converted && <span> · your mark is out of {a.marking_scale_value}</span>}
                {a.weight ? ` · weight ${a.weight}%` : ''}
                {a.published_at ? ` · released ${new Date(a.published_at).toLocaleDateString()}` : ''}
              </p>
            </div>
            <div className="text-right">
              <p className="text-xs text-text-secondary">Your score</p>
              <p className="text-2xl font-bold text-text-primary">
                {a.my_mark?.reported_score ?? a.my_mark?.score ?? '—'}
                <span className="text-sm font-normal text-text-secondary"> / {a.maximum_score}</span>
              </p>
            </div>
          </div>

          {a.my_mark?.comment && (
            <p className="mt-3 text-sm text-text-secondary bg-page-bg rounded-lg p-3">{a.my_mark.comment}</p>
          )}

          {a.my_mark?.dispute_status === 'OPEN' && (
            <p className="mt-3 text-sm text-amber-700 bg-amber-50 border border-amber-200 rounded-lg px-3 py-2">
              You reported: &ldquo;{a.my_mark.dispute_reason}&rdquo; — waiting for your lecturer.
            </p>
          )}
          {a.my_mark?.dispute_status === 'RESOLVED' && (
            <div className="mt-3 text-sm text-green-700 bg-green-50 border border-green-200 rounded-lg px-3 py-2">
              <span className="font-semibold">Lecturer replied: </span>{a.my_mark.dispute_response}
            </div>
          )}

          <div className="mt-3">
            <ReportDispute assessment={a} onDone={load} />
          </div>
        </div>
      ))}
    </div>
  );
};

const ReportDispute = ({ assessment, onDone }) => {
  const [open, setOpen] = useState(false);
  const [text, setText] = useState('');
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState('');

  const status = assessment.my_mark?.dispute_status;
  if (!assessment.my_mark || status === 'OPEN' || status === 'RESOLVED') return null;

  const submit = async () => {
    if (!text.trim()) {
      setErr('Tell your lecturer what is wrong.');
      return;
    }
    setBusy(true);
    try {
      await learningApi.raiseDispute(assessment.my_mark.id, text.trim());
      setOpen(false);
      setText('');
      setErr('');
      onDone();
    } catch (e) {
      setErr(e.response?.data?.error?.message || 'Could not send the report.');
    } finally {
      setBusy(false);
    }
  };

  if (!open) {
    return (
      <button
        onClick={() => setOpen(true)}
        className="text-sm text-primary hover:underline flex items-center gap-1.5"
      >
        <TrendingUp size={15} /> This mark looks wrong — report it
      </button>
    );
  }

  return (
    <div className="p-4 rounded-xl bg-page-bg border border-border-default space-y-2">
      <textarea
        value={text}
        onChange={(e) => setText(e.target.value)}
        className="fet-input min-h-[70px]"
        placeholder="Explain what is wrong with this mark…"
      />
      {err && <p className="text-xs text-red-600">{err}</p>}
      <div className="flex justify-end gap-2">
        <button onClick={() => setOpen(false)} className="fet-btn-secondary text-sm">Cancel</button>
        <button onClick={submit} disabled={busy} className="fet-btn-primary text-sm">
          {busy ? <Loader2 size={14} className="animate-spin" /> : null} Send report
        </button>
      </div>
    </div>
  );
};

const ContinuousAssessment = ({ user }) => {
  const role = normalizeRole(user?.role);
  const isStaff = role === 'lecturer' || role === 'admin';
  return isStaff ? <StaffAssessments user={user} /> : <StudentAssessments user={user} />;
};

export default ContinuousAssessment;
