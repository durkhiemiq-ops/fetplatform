import React, { useMemo, useState } from 'react';
import { Search, CheckCircle, Plus, AlertCircle } from 'lucide-react';
import { useAppContext } from '../../context/AppContext';

/**
 * CourseCatalogue — backed entirely by the API.
 *
 * M3: this previously built its list from a hardcoded `baseCourseList` plus
 * `mockCourses` and toggled enrollment in localStorage. Enrolling therefore
 * created NO Enrollment row, so it had no effect on attendance eligibility —
 * the UI implied an action the server never saw. Courses now come from
 * GET /academic/courses/ and Enrol/Drop call POST/DELETE /academic/enrollments/,
 * which is the sole source of attendance eligibility (BR-010/BR-011/BR-012).
 */
const CourseCatalogue = ({ user }) => {
  const { courses, enrollments, enroll, drop, loading } = useAppContext();

  const [searchTerm, setSearchTerm] = useState('');
  const [activeTab, setActiveTab] = useState('all');
  const [filterDepartment, setFilterDepartment] = useState('all');
  const [busyCourse, setBusyCourse] = useState(null);
  const [notice, setNotice] = useState(null);
  const [error, setError] = useState('');

  const isStudent = (user?.role || '').toLowerCase() === 'student';
  const enrolledIds = useMemo(
    () => new Set((enrollments || []).map((e) => e.course)),
    [enrollments]
  );

  const departments = useMemo(() => {
    const names = courses.map((c) => c.departmentName).filter(Boolean);
    return [...new Set(names)].sort();
  }, [courses]);

  const matchesSearch = (c) =>
    !searchTerm ||
    c.code.toLowerCase().includes(searchTerm.toLowerCase()) ||
    (c.name || '').toLowerCase().includes(searchTerm.toLowerCase());

  const filtered = useMemo(
    () =>
      courses.filter(
        (c) => matchesSearch(c) && (filterDepartment === 'all' || c.departmentName === filterDepartment)
      ),
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [courses, searchTerm, filterDepartment]
  );

  const myCourses = useMemo(
    () => filtered.filter((c) => enrolledIds.has(c.id)),
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [filtered, enrolledIds]
  );

  const displayed = isStudent && activeTab === 'mine' ? myCourses : filtered;

  const handleToggle = async (course) => {
    setBusyCourse(course.id);
    setError('');
    setNotice(null);
    try {
      if (enrolledIds.has(course.id)) {
        await drop(course.id);
        setNotice(`Dropped ${course.code}. Attendance eligibility ended for future classes.`);
      } else {
        await enroll(course.id);
        setNotice(`Enrolled in ${course.code}.`);
      }
      setTimeout(() => setNotice(null), 4000);
    } catch (err) {
      setError(err.message || 'Could not update your enrollment.');
    } finally {
      setBusyCourse(null);
    }
  };

  if (loading) {
    return <p className="py-8 text-center text-sm text-text-secondary">Loading courses…</p>;
  }

  return (
    <div className="space-y-6">
      <div>
        <h2 className="text-2xl font-bold text-text-primary">Course Catalogue</h2>
        <p className="text-text-secondary" style={{ fontSize: '14px' }}>
          {isStudent
            ? `You are enrolled in ${enrolledIds.size} course${enrolledIds.size === 1 ? '' : 's'}. Enrollment determines attendance eligibility.`
            : 'Browse all FET courses'}
        </p>
      </div>

      {notice && (
        <div className="flex items-center gap-2 rounded-lg border border-green-200 bg-green-50 px-4 py-2.5 text-[13px] text-green-800">
          <CheckCircle size={14} /> {notice}
        </div>
      )}
      {error && (
        <div className="flex items-center gap-2 rounded-lg border border-red-200 bg-red-50 px-4 py-2.5 text-[13px] text-red-700">
          <AlertCircle size={14} /> {error}
        </div>
      )}

      {isStudent && (
        <div className="flex gap-2 border-b border-border-default">
          <button
            onClick={() => setActiveTab('all')}
            className={`px-4 py-2 text-sm font-semibold border-b-2 -mb-px transition-colors ${
              activeTab === 'all'
                ? 'border-primary text-primary'
                : 'border-transparent text-text-secondary hover:text-text-primary'
            }`}
          >
            All Courses ({courses.length})
          </button>
          <button
            onClick={() => setActiveTab('mine')}
            className={`px-4 py-2 text-sm font-semibold border-b-2 -mb-px transition-colors ${
              activeTab === 'mine'
                ? 'border-primary text-primary'
                : 'border-transparent text-text-secondary hover:text-text-primary'
            }`}
          >
            My Courses ({myCourses.length})
          </button>
        </div>
      )}

      <div className="flex flex-col sm:flex-row gap-4">
        <div className="relative flex-1">
          <Search className="absolute left-3 top-1/2 transform -translate-y-1/2 text-text-secondary" size={18} />
          <input
            type="text"
            placeholder="Search courses..."
            value={searchTerm}
            onChange={(e) => setSearchTerm(e.target.value)}
            className="w-full pl-10 pr-4 py-2 fet-input"
          />
        </div>

        {!(isStudent && activeTab === 'mine') && departments.length > 0 && (
          <select
            value={filterDepartment}
            onChange={(e) => setFilterDepartment(e.target.value)}
            className="px-4 py-2 fet-select"
          >
            <option value="all">All Departments</option>
            {departments.map((dept) => (
              <option key={dept} value={dept}>{dept}</option>
            ))}
          </select>
        )}
      </div>

      <div className="fet-card overflow-hidden">
        <div className="overflow-x-auto">
          <table className="w-full fet-table">
            <thead>
              <tr className="bg-page-bg border-b border-border-default">
                <th className="text-left py-3 px-4 text-xs font-semibold text-text-secondary uppercase">Code</th>
                <th className="text-left py-3 px-4 text-xs font-semibold text-text-secondary uppercase">Title</th>
                <th className="text-left py-3 px-4 text-xs font-semibold text-text-secondary uppercase">Department</th>
                <th className="text-left py-3 px-4 text-xs font-semibold text-text-secondary uppercase">Faculty</th>
                {isStudent && (
                  <th className="text-right py-3 px-4 text-xs font-semibold text-text-secondary uppercase">Enrollment</th>
                )}
              </tr>
            </thead>
            <tbody>
              {displayed.map((course) => {
                const isEnrolled = enrolledIds.has(course.id);
                return (
                  <tr
                    key={course.id}
                    className={`border-b border-border-default transition-colors ${
                      isEnrolled ? 'bg-green-50/60 hover:bg-green-50' : 'hover:bg-page-bg'
                    }`}
                  >
                    <td className="py-3 px-4 font-mono font-semibold text-primary text-sm">{course.code}</td>
                    <td className="py-3 px-4 text-text-primary" style={{ fontSize: '14px' }}>{course.name}</td>
                    <td className="py-3 px-4 text-text-secondary" style={{ fontSize: '13px' }}>
                      {course.departmentName || '—'}
                    </td>
                    <td className="py-3 px-4 text-text-secondary" style={{ fontSize: '13px' }}>
                      {course.facultyName || '—'}
                    </td>
                    {isStudent && (
                      <td className="py-3 px-4 text-right">
                        {isEnrolled ? (
                          <div className="flex items-center justify-end gap-3">
                            <span className="fet-badge fet-badge-active inline-flex items-center gap-1">
                              <CheckCircle size={12} /> Enrolled
                            </span>
                            <button
                              onClick={() => handleToggle(course)}
                              disabled={busyCourse === course.id}
                              className="text-xs text-red-500 hover:underline font-medium disabled:opacity-50"
                            >
                              {busyCourse === course.id ? 'Working…' : 'Drop'}
                            </button>
                          </div>
                        ) : (
                          <button
                            onClick={() => handleToggle(course)}
                            disabled={busyCourse === course.id}
                            className="fet-btn-primary inline-flex items-center gap-1 text-xs disabled:opacity-50"
                          >
                            <Plus size={12} />
                            {busyCourse === course.id ? 'Enrolling…' : 'Enrol'}
                          </button>
                        )}
                      </td>
                    )}
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
        {displayed.length === 0 && (
          <div className="text-center py-8 text-text-secondary">
            {courses.length === 0
              ? 'No courses have been created yet.'
              : isStudent && activeTab === 'mine'
              ? 'You are not enrolled in any course yet. Use the All Courses tab to enrol.'
              : 'No courses match your search.'}
          </div>
        )}
      </div>
    </div>
  );
};

export default CourseCatalogue;
