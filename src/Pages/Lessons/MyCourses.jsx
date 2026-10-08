import React, { useState, useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import { Loader2, BookOpen, Users, FileText, ArrowRight, Plus, X, CheckCircle2, AlertTriangle, Search } from 'lucide-react';
import { learningApi } from '../../lib/learning';
import { normalizeRole } from '../../lib/profile';
import {
  SectionHeader, Card, CardBody, CardFoot, CourseBanner, CourseFigures,
  Eyebrow, Pill, Tag, Bar, EmptyState, Callout,
} from '../../components/UI';

const MyCourses = ({ user }) => {
  const [courses, setCourses] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [query, setQuery] = useState('');
  const navigate = useNavigate();

  const role = normalizeRole(user?.role);
  const isStaff = role === 'lecturer' || role === 'admin';

  const [showCreate, setShowCreate] = useState(false);
  const [available, setAvailable] = useState(null);
  const [selectedOffering, setSelectedOffering] = useState('');
  const [className, setClassName] = useState('');
  const [classType, setClassType] = useState('LECTURE');
  const [location, setLocation] = useState('');
  const [creating, setCreating] = useState(false);
  const [createError, setCreateError] = useState('');
  const [created, setCreated] = useState(null);
  const [readback, setReadback] = useState(null);

  const resetCreate = () => {
    setCreateError('');
    setCreated(null);
    setReadback(null);
    setSelectedOffering('');
    setClassName('');
    setClassType('LECTURE');
    setLocation('');
    setAvailable(null);
  };

  const openCreate = async () => {
    setShowCreate(true);
    resetCreate();
    try {
      const data = await learningApi.availableClassroomCourses();
      setAvailable(data);
    } catch (err) {
      setCreateError(err.response?.data?.error?.message || 'Could not load your courses.');
    }
  };

  const selected = available?.courses?.find((c) => c.offering_id === selectedOffering);

  const handleCreate = async () => {
    // Pending-state guard: the submit button is disabled too, but a second
    // click must not slip through a re-render while the first is in flight.
    if (creating || !selectedOffering || !className.trim()) return;
    setCreating(true);
    setCreateError('');
    try {
      const payload = { name: className.trim(), class_type: classType };
      const where = location.trim();
      if (where) payload.location = where;
      const result = await learningApi.createClass(selectedOffering, payload);
      setCreated(result);
      // Read the row straight back rather than trusting the echo of what was
      // just posted — this is the server's persisted identity for the class.
      try {
        const rows = await learningApi.listClasses(selectedOffering);
        setReadback((rows || []).find((row) => row.id === result?.id) || null);
      } catch (err) {
        setReadback(null);
      }
    } catch (err) {
      setCreateError(err.response?.data?.error?.message || 'Could not create the class.');
    } finally {
      setCreating(false);
    }
  };

  useEffect(() => {
    let cancelled = false;
    const load = async () => {
      setLoading(true);
      setError('');
      try {
        const data = await learningApi.getMyCourses(user?.role || 'student');
        if (!cancelled) setCourses(data || []);
      } catch (err) {
        if (!cancelled) setError('Failed to load your courses. Please try again.');
      } finally {
        if (!cancelled) setLoading(false);
      }
    };
    load();
    return () => { cancelled = true; };
  }, [user]);

  const openCourse = (course) => {
    // A row without an offering id cannot address a detail page: navigating
    // would land on /lessons/undefined. The backend sends offering_id on
    // every row (see tests_offering_id_contract), so a missing one is corrupt
    // data, not a state to navigate from.
    if (!course?.offering_id) return;
    navigate(`/lessons/${course.offering_id}`);
  };

  const term = query.trim().toLowerCase();
  const visible = term
    ? courses.filter((c) => (
      (c.course_code || '').toLowerCase().includes(term)
      || (c.course_title || '').toLowerCase().includes(term)
      || (c.lecturer_name || '').toLowerCase().includes(term)
    ))
    : courses;

  return (
    <div className="space-y-4">
      <SectionHeader
        area="classrooms"
        icon={BookOpen}
        title="Classrooms"
        subtitle={isStaff
          ? 'Courses you teach. Each one holds the materials, assignments and marks for that course.'
          : 'Courses you are enrolled in this semester.'}
        crumb={[{ label: 'FET Platform' }, { label: 'Classrooms' }]}
        actions={isStaff ? (
          <button type="button" onClick={openCreate} className="fet-btn-primary">
            <Plus size={15} /> Create class
          </button>
        ) : null}
      />

      {error ? <Callout tone="bd" icon={AlertTriangle}>{error}</Callout> : null}

      {!loading && courses.length > 0 ? (
        <div className="mb-4 flex flex-wrap items-center gap-2">
          <div className="relative min-w-[200px] flex-1 sm:max-w-[280px]">
            <Search size={15} className="absolute left-3 top-1/2 -translate-y-1/2 text-text-muted" />
            <input
              type="text"
              value={query}
              onChange={(e) => setQuery(e.target.value)}
              placeholder="Search classrooms"
              className="fet-input pl-9"
            />
          </div>
          <Tag>{visible.length} of {courses.length} classrooms</Tag>
        </div>
      ) : null}

      {loading ? (
        <div className="flex justify-center py-16">
          <Loader2 size={26} className="animate-spin text-primary" />
        </div>
      ) : null}

      {!loading && courses.length === 0 ? (
        <Card>
          <EmptyState
            icon={BookOpen}
            title={isStaff ? 'No courses assigned yet' : 'You are not enrolled in any courses'}
            subtitle={isStaff
              ? 'Courses appear here once you are assigned to an offering.'
              : 'Your enrolled courses for the active semester appear here.'}
            action={isStaff ? (
              <button type="button" onClick={openCreate} className="fet-btn-primary">
                <Plus size={15} /> Create class
              </button>
            ) : null}
          />
        </Card>
      ) : null}

      {!loading && courses.length > 0 && visible.length === 0 ? (
        <Card>
          <EmptyState
            icon={Search}
            title="No classroom matches that search"
            subtitle="Try a course code, a course title, or a lecturer name."
          />
        </Card>
      ) : null}

      {visible.length > 0 ? (
        <div className="grid grid-cols-1 gap-4 lg:grid-cols-2">
          {visible.map((course) => {
            // The lecturer endpoint carries cohort and schedule data; the student
            // one does not, so the card only shows what it was actually given.
            const cohort = course.enrolled_students ?? null;
            const figures = isStaff
              ? [
                { label: 'Students', value: cohort ?? 0 },
                { label: 'Materials', value: course.materials_count ?? 0 },
                { label: 'Assignments', value: course.assignments_count ?? 0 },
                { label: 'Assessments', value: course.assessments_count ?? 0 },
              ]
              : [
                { label: 'Materials', value: course.materials_count ?? 0 },
                { label: 'Assignments', value: course.assignments_count ?? 0 },
                { label: 'Announcements', value: course.announcements_count ?? 0 },
                { label: 'Department', value: course.department || '—' },
              ];
            const slots = course.schedules?.length || 0;
            const types = (course.class_definitions || [])
              .map((c) => c.class_type)
              .filter(Boolean);
            return (
              <Card key={course.offering_id} className="ui-course-card">
                <CourseBanner
                  code={course.course_code}
                  title={course.course_title}
                  meta={`${course.lecturer_name || 'Staff'} · ${course.semester || 'Active semester'}`}
                />
                <CourseFigures items={figures} />
                {isStaff && cohort !== null ? (
                  <CardBody style={{ borderBottom: '1px solid rgb(var(--line))' }}>
                    <div className="mb-2 flex items-center">
                      <Eyebrow>Cohort registered</Eyebrow>
                      <div className="flex-1" />
                      <span className="num text-[11.5px] text-text-secondary">
                        {cohort} student{cohort === 1 ? '' : 's'}
                      </span>
                    </div>
                    <Bar value={cohort > 0 ? 100 : 0} tone={cohort > 0 ? 'ok' : 'wn'} />
                  </CardBody>
                ) : null}
                <CardFoot>
                  <div className="flex flex-wrap items-center gap-2">
                    {types.length ? <Tag>{types.join(' and ')}</Tag> : null}
                    {slots ? <Tag>{slots} weekly slot{slots === 1 ? '' : 's'}</Tag> : null}
                    {(course.materials_count ?? 0) === 0 ? (
                      <Pill tone="in">No materials yet</Pill>
                    ) : null}
                    {isStaff && course.open_disputes > 0 ? (
                      <Pill tone="bd">{course.open_disputes} dispute{course.open_disputes === 1 ? '' : 's'}</Pill>
                    ) : null}
                    {isStaff && course.ungraded_submissions > 0 ? (
                      <Pill tone="wn">{course.ungraded_submissions} to mark</Pill>
                    ) : null}
                  </div>
                  <button
                    type="button"
                    onClick={() => openCourse(course)}
                    className="fet-btn-primary"
                  >
                    Open <ArrowRight size={15} />
                  </button>
                </CardFoot>
              </Card>
            );
          })}
        </div>
      ) : null}

      {showCreate && (
        <div className="fixed inset-0 bg-black/50 backdrop-blur-sm flex items-center justify-center z-50 p-4">
          <div className="fet-card bg-white rounded-2xl shadow-modal w-full max-w-lg">
            <div className="flex items-center justify-between p-5 border-b border-border-default">
              <div>
                <h3 className="text-lg font-bold text-text-primary">Create class</h3>
                <p className="text-xs text-text-secondary mt-0.5">
                  Add a class to a course offering you already teach.
                </p>
              </div>
              <button onClick={() => setShowCreate(false)} className="p-1 hover:bg-page-bg rounded-lg">
                <X size={22} className="text-text-secondary" />
              </button>
            </div>

            <div className="p-5 space-y-4">
              {createError && (
                <div className="bg-red-50 border border-red-200 text-red-700 px-3 py-2 rounded-lg text-sm flex items-start gap-2">
                  <AlertTriangle size={16} className="mt-0.5 shrink-0" />
                  <span>{createError}</span>
                </div>
              )}

              {created ? (
                <div className="space-y-4">
                  <div className="bg-green-50 border border-green-200 text-green-800 px-4 py-3 rounded-lg text-sm flex items-start gap-2">
                    <CheckCircle2 size={18} className="mt-0.5 shrink-0" />
                    <div>
                      <p className="font-semibold">{created.name} is ready</p>
                      <p className="mt-0.5">
                        {created.course_code} — {created.course_title}
                        {created.day_of_week ? ` · ${created.day_of_week}` : ''}
                      </p>
                      <p className="mt-1 num text-[11.5px]">
                        {readback ? `Saved as ${readback.id}` : `Created as ${created.id}`}
                      </p>
                    </div>
                  </div>
                  <div className="flex justify-end gap-2">
                    <button onClick={() => setShowCreate(false)} className="fet-btn-secondary">Close</button>
                    <button
                      onClick={() => { setShowCreate(false); navigate(`/lessons/${selectedOffering}`); }}
                      className="fet-btn-primary flex items-center gap-2"
                    >
                      Open course <ArrowRight size={15} />
                    </button>
                  </div>
                </div>
              ) : (
                <>
                  <div>
                    <label className="fet-label">Course offering</label>
                    {!available ? (
                      <div className="flex items-center gap-2 text-text-secondary text-sm py-3">
                        <Loader2 size={16} className="animate-spin" /> Loading your courses...
                      </div>
                    ) : available.courses.length === 0 ? (
                      <p className="text-sm text-text-secondary py-3">
                        You have no courses assigned yet. Ask your department admin to assign you a course.
                      </p>
                    ) : (
                      <div className="space-y-2 max-h-56 overflow-y-auto pr-1">
                        {available.courses.map((c) => (
                          <button
                            key={c.offering_id}
                            type="button"
                            onClick={() => setSelectedOffering(c.offering_id)}
                            className={`w-full text-left p-3 rounded-xl border transition-colors ${
                              selectedOffering === c.offering_id
                                ? 'border-primary bg-primary/5'
                                : 'border-border-default hover:border-primary'
                            }`}
                          >
                            <div className="flex items-center justify-between gap-2">
                              <span className="font-semibold text-text-primary text-sm">
                                {c.course_code} — {c.course_title}
                              </span>
                              <span className="text-[11px] px-2 py-0.5 rounded-full bg-page-bg text-text-secondary shrink-0">
                                {c.semester || 'Active semester'}
                              </span>
                            </div>
                            <p className="text-xs text-text-secondary mt-0.5">
                              {c.department ? `${c.department} · ` : ''}
                              {c.lecturer_name || 'Unassigned'}
                            </p>
                          </button>
                        ))}
                      </div>
                    )}
                  </div>

                  <div>
                    <label className="fet-label" htmlFor="class-name">Class name</label>
                    <input
                      id="class-name"
                      type="text"
                      value={className}
                      onChange={(e) => setClassName(e.target.value)}
                      placeholder="e.g. Week 1 lecture"
                      maxLength={255}
                      className="fet-input"
                    />
                  </div>

                  <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
                    <div>
                      <label className="fet-label" htmlFor="class-type">Class type</label>
                      <select
                        id="class-type"
                        value={classType}
                        onChange={(e) => setClassType(e.target.value)}
                        className="fet-input"
                      >
                        <option value="LECTURE">Lecture</option>
                        <option value="LAB">Lab</option>
                        <option value="TUTORIAL">Tutorial</option>
                        <option value="SEMINAR">Seminar</option>
                        <option value="WORKSHOP">Workshop</option>
                        <option value="OTHER">Other</option>
                      </select>
                    </div>
                    <div>
                      <label className="fet-label" htmlFor="class-location">Location (optional)</label>
                      <input
                        id="class-location"
                        type="text"
                        value={location}
                        onChange={(e) => setLocation(e.target.value)}
                        placeholder="e.g. LT-2"
                        maxLength={255}
                        className="fet-input"
                      />
                    </div>
                  </div>

                  {selected ? (
                    <p className="text-xs text-text-secondary bg-page-bg rounded-lg p-3 flex items-start gap-2">
                      <Users size={14} className="mt-0.5 shrink-0" />
                      <span>
                        This adds a class to <strong>{selected.course_code} — {selected.course_title}</strong>
                        {selected.semester ? ` (${selected.semester})` : ''}. Students only see it if they
                        are actively enrolled in this offering. No students, materials or marks are
                        copied, and no one is enrolled for you.
                      </span>
                    </p>
                  ) : null}

                  <div className="flex justify-end gap-2">
                    <button onClick={() => setShowCreate(false)} className="fet-btn-secondary">Cancel</button>
                    <button
                      onClick={handleCreate}
                      disabled={creating || !selectedOffering || !className.trim()}
                      className="fet-btn-primary flex items-center gap-2"
                    >
                      {creating ? <Loader2 size={16} className="animate-spin" /> : <Plus size={16} />}
                      {creating ? 'Creating...' : 'Create class'}
                    </button>
                  </div>
                </>
              )}
            </div>
          </div>
        </div>
      )}
    </div>
  );
};

export default MyCourses;