import React, { useState, useEffect, useCallback } from 'react';
import {
  Users, QrCode, Award, AlertTriangle, BookOpen, ArrowRight, Plus, Loader2,
  MessageSquare, ClipboardCheck, Megaphone, FileText, Calendar, Clock, MapPin,
  TrendingUp, Layers, CheckCircle2, UserCheck, LayoutDashboard, AlertCircle,
} from 'lucide-react';
import { useNavigate } from 'react-router-dom';
import { SectionHeader, Callout } from '../UI';
import StatsCard from './StatsCard';
import attendanceApi from '../../lib/attendance';

const DAYS = ['SUNDAY', 'MONDAY', 'TUESDAY', 'WEDNESDAY', 'THURSDAY', 'FRIDAY', 'SATURDAY'];

const fmtTime = (t) => (t ? String(t).slice(0, 5) : '');

const dayLabel = (d) => (d ? d.charAt(0) + d.slice(1).toLowerCase() : '');

const LecturerDashboard = ({ user }) => {
  const navigate = useNavigate();
  const lecturerName = user?.fullName || 'Lecturer';

  const [courses, setCourses] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');

  const load = useCallback(async () => {
    setLoading(true);
    setError('');
    try {
      const data = await attendanceApi.lecturerCourses();
      setCourses(Array.isArray(data) ? data : []);
    } catch {
      setError('Could not load your teaching data.');
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { load(); }, [load]);

  const totals = courses.reduce(
    (acc, c) => ({
      students: acc.students + (c.enrolled_students || 0),
      ungraded: acc.ungraded + (c.ungraded_submissions || 0),
      disputes: acc.disputes + (c.open_disputes || 0),
      assessments: acc.assessments + (c.assessments_count || 0),
    }),
    { students: 0, ungraded: 0, disputes: 0, assessments: 0 },
  );

  const today = DAYS[new Date().getDay()];
  const todaysClasses = courses.flatMap((c) =>
    (c.schedules || [])
      .filter((s) => s.day_of_week === today)
      .map((s) => ({ ...s, course_code: c.course_code, offering_id: c.offering_id, location: s.location })),
  ).sort((a, b) => String(a.start_time).localeCompare(String(b.start_time)));

  const attention = courses.filter(
    (c) => (c.ungraded_submissions || 0) > 0 || (c.open_disputes || 0) > 0,
  );

  if (loading) {
    return (
      <div className="flex flex-col items-center justify-center py-24 gap-3">
        <Loader2 className="h-8 w-8 animate-spin text-primary" />
        <p className="text-sm text-text-secondary">Loading your teaching workspace…</p>
      </div>
    );
  }

  return (
    <div className="space-y-4">
      <SectionHeader
        area="hub"
        icon={LayoutDashboard}
        title={lecturerName}
        subtitle={`${user?.department || 'Department'} · ${user?.title || 'Lecturer'} · ${courses.length} course${courses.length === 1 ? '' : 's'} · ${totals.students} student${totals.students === 1 ? '' : 's'}`}
        crumb={[{ label: 'FET Platform' }, { label: 'Dashboard' }]}
        actions={(
          <>
            <button type="button" onClick={() => navigate('/lessons')} className="fet-btn-secondary">
              <Plus size={15} /> New classroom
            </button>
            <button type="button" onClick={() => navigate('/attendance')} className="fet-btn-primary">
              <QrCode size={15} /> Take attendance
            </button>
          </>
        )}
      />

      {error ? (
        <Callout tone="bd" icon={AlertCircle}>
          <div className="flex items-center justify-between gap-3">
            <span>{error}</span>
            <button type="button" onClick={load} className="font-medium underline">Retry</button>
          </div>
        </Callout>
      ) : null}

      {/* Teaching load */}
      <div className="grid grid-cols-2 lg:grid-cols-4 gap-3 md:gap-4">
        <StatsCard icon={BookOpen} label="Courses Taught" value={courses.length} color="primary" />
        <StatsCard icon={Users} label="Students Taught" value={totals.students} color="secondary" />
        <StatsCard
          icon={ClipboardCheck}
          label="To Grade"
          value={totals.ungraded}
          color={totals.ungraded > 0 ? 'warning' : 'secondary'}
        />
        <StatsCard
          icon={AlertTriangle}
          label="Mark Disputes"
          value={totals.disputes}
          color={totals.disputes > 0 ? 'error' : 'secondary'}
        />
      </div>

      <div className="grid grid-cols-1 xl:grid-cols-3 gap-4 md:gap-5">
        {/* Main column */}
        <div className="xl:col-span-2 space-y-4 md:space-y-5">
          {/* Needs attention */}
          {attention.length > 0 && (
            <div className="fet-card p-5">
              <h3 className="text-[15px] font-semibold text-text-primary flex items-center gap-2">
                <TrendingUp size={16} className="text-warning" /> Needs your attention
              </h3>
              <p className="text-xs text-text-secondary mt-0.5 mb-4">
                Work waiting on you across your courses.
              </p>
              <div className="space-y-2">
                {attention.map((c) => (
                  <button
                    key={c.offering_id}
                    onClick={() => navigate(`/lessons/${c.offering_id}`)}
                    className="w-full flex items-center justify-between gap-3 p-3 rounded-xl bg-page-bg border border-transparent hover:border-border-default hover:bg-primary/5 text-left transition-colors"
                  >
                    <div className="flex items-center gap-2.5 min-w-0">
                      <span className="font-semibold text-text-primary text-sm shrink-0">{c.course_code}</span>
                      <span className="text-sm text-text-secondary truncate">{c.course_title}</span>
                    </div>
                    <div className="flex items-center gap-2 shrink-0">
                      {c.ungraded_submissions > 0 && (
                        <span className="text-xs px-2 py-1 rounded-full bg-amber-50 text-amber-700 border border-amber-200">
                          {c.ungraded_submissions} to grade
                        </span>
                      )}
                      {c.open_disputes > 0 && (
                        <span className="text-xs px-2 py-1 rounded-full bg-red-50 text-red-700 border border-red-200">
                          {c.open_disputes} dispute{c.open_disputes === 1 ? '' : 's'}
                        </span>
                      )}
                      <ArrowRight size={15} className="text-text-secondary" />
                    </div>
                  </button>
                ))}
              </div>
            </div>
          )}

          {/* My classrooms */}
          <div className="fet-card p-5">
            <div className="flex items-center justify-between mb-4">
              <h3 className="text-[15px] font-semibold text-text-primary flex items-center gap-2">
                <BookOpen size={16} className="text-primary" /> My Classrooms
              </h3>
              <button
                onClick={() => navigate('/lessons')}
                className="text-xs text-primary font-semibold hover:opacity-80"
              >
                Manage →
              </button>
            </div>

            {courses.length === 0 ? (
              <div className="text-center py-10">
                <BookOpen size={40} className="mx-auto text-text-secondary opacity-40" />
                <p className="text-sm text-text-secondary mt-3">No classrooms yet</p>
                <button onClick={() => navigate('/lessons')} className="fet-btn-primary mt-4">
                  Create your first classroom
                </button>
              </div>
            ) : (
              <div className="space-y-3">
                {courses.map((c) => (
                  <div
                    key={c.offering_id}
                    className="p-4 rounded-xl bg-page-bg border border-transparent hover:border-border-default transition-colors"
                  >
                    <div className="flex items-start justify-between gap-3">
                      <div className="min-w-0">
                        <p className="font-semibold text-text-primary text-sm">{c.course_code}</p>
                        <p className="text-sm text-text-secondary">{c.course_title}</p>
                      </div>
                      <div className="flex items-center gap-2 shrink-0">
                        <button
                          onClick={() => navigate(`/lessons/${c.offering_id}`)}
                          className="text-primary text-xs font-semibold flex items-center gap-1 hover:underline"
                        >
                          Open <ArrowRight size={14} />
                        </button>
                      </div>
                    </div>

                    <div className="mt-3 pt-3 border-t border-border-default flex flex-wrap items-center gap-x-4 gap-y-1.5 text-xs text-text-secondary">
                      <span className="flex items-center gap-1"><Users size={13} /> {c.enrolled_students} students</span>
                      <span className="flex items-center gap-1"><FileText size={13} /> {c.materials_count} materials</span>
                      <span className="flex items-center gap-1"><ClipboardCheck size={13} /> {c.assignments_count} assignments</span>
                      <span className="flex items-center gap-1"><Award size={13} /> {c.assessments_count} assessments</span>
                      <span className="flex items-center gap-1"><Megaphone size={13} /> {c.announcements_count} posts</span>
                    </div>

                    <div className="mt-3 flex flex-wrap gap-2">
                      <button
                        onClick={() => navigate(`/lessons/${c.offering_id}`)}
                        className="text-xs px-2.5 py-1.5 rounded-lg border border-border-default text-text-primary hover:bg-white flex items-center gap-1.5"
                      >
                        <FileText size={13} /> Materials
                      </button>
                      <button
                        onClick={() => navigate(`/lessons/${c.offering_id}`)}
                        className="text-xs px-2.5 py-1.5 rounded-lg border border-border-default text-text-primary hover:bg-white flex items-center gap-1.5"
                      >
                        <ClipboardCheck size={13} /> Assignments
                      </button>
                      <button
                        onClick={() => navigate(`/assessment`)}
                        className="text-xs px-2.5 py-1.5 rounded-lg border border-border-default text-text-primary hover:bg-white flex items-center gap-1.5"
                      >
                        <Award size={13} /> Marks
                      </button>
                      <button
                        onClick={() => navigate(`/attendance`)}
                        className="text-xs px-2.5 py-1.5 rounded-lg border border-border-default text-text-primary hover:bg-white flex items-center gap-1.5"
                      >
                        <QrCode size={13} /> Attendance
                      </button>
                    </div>
                  </div>
                ))}
              </div>
            )}
          </div>
        </div>

        {/* Side column */}
        <div className="space-y-4 md:space-y-5">
          {/* Today's timetable */}
          <div className="fet-card p-5">
            <h3 className="text-[15px] font-semibold text-text-primary flex items-center gap-2 mb-3">
              <Calendar size={16} className="text-primary" /> Today · {dayLabel(today)}
            </h3>
            {todaysClasses.length === 0 ? (
              <div className="text-center py-6">
                <CheckCircle2 size={30} className="mx-auto text-success/50" />
                <p className="text-sm text-text-secondary mt-2">No classes scheduled today</p>
              </div>
            ) : (
              <div className="space-y-2">
                {todaysClasses.map((s, i) => (
                  <div key={`${s.id}-${i}`} className="p-3 rounded-xl bg-page-bg">
                    <div className="flex items-center justify-between gap-2">
                      <span className="font-semibold text-text-primary text-sm">{s.course_code}</span>
                      <span className="text-xs text-text-secondary font-mono">
                        {fmtTime(s.start_time)}–{fmtTime(s.end_time)}
                      </span>
                    </div>
                    <p className="text-xs text-text-secondary mt-1 flex items-center gap-1">
                      <MapPin size={12} /> {s.location || 'Room TBC'}
                    </p>
                  </div>
                ))}
              </div>
            )}
          </div>

          {/* Assessment overview */}
          <div className="fet-card p-5">
            <h3 className="text-[15px] font-semibold text-text-primary flex items-center gap-2 mb-3">
              <Award size={16} className="text-primary" /> Assessment
            </h3>
            <div className="grid grid-cols-2 gap-3 mb-3">
              <div className="p-3 rounded-xl bg-page-bg text-center">
                <p className="text-xl font-bold text-text-primary">{totals.assessments}</p>
                <p className="text-[11px] text-text-secondary">Sheets created</p>
              </div>
              <div className="p-3 rounded-xl bg-page-bg text-center">
                <p className={`text-xl font-bold ${totals.disputes > 0 ? 'text-danger' : 'text-text-primary'}`}>
                  {totals.disputes}
                </p>
                <p className="text-[11px] text-text-secondary">Student queries</p>
              </div>
            </div>
            <button
              onClick={() => navigate('/assessment')}
              className="w-full fet-btn-secondary flex items-center justify-center gap-2 text-sm"
            >
              <Layers size={15} /> Enter marks &amp; combined grades
            </button>
          </div>

          {/* Students */}
          <div className="fet-card p-5">
            <h3 className="text-[15px] font-semibold text-text-primary flex items-center gap-2 mb-3">
              <UserCheck size={16} className="text-primary" /> My students
            </h3>
            <div className="space-y-2">
              {courses.filter((c) => c.enrolled_students > 0).map((c) => (
                <button
                  key={c.offering_id}
                  onClick={() => navigate(`/lessons/${c.offering_id}`)}
                  className="w-full flex items-center justify-between gap-2 p-2.5 rounded-lg hover:bg-page-bg text-left transition-colors"
                >
                  <span className="text-sm text-text-primary font-medium">{c.course_code}</span>
                  <span className="text-xs text-text-secondary flex items-center gap-1">
                    <Users size={12} /> {c.enrolled_students}
                  </span>
                </button>
              ))}
              {courses.length === 0 && (
                <p className="text-sm text-text-secondary text-center py-3">No students yet</p>
              )}
            </div>
          </div>
        </div>
      </div>
    </div>
  );
};

export default LecturerDashboard;
