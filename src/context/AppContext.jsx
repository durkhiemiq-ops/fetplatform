import React, { createContext, useContext, useState, useEffect, useCallback, useMemo } from 'react';

// The AppContext keeps its public interface (all the names it exported before
// the API wiring) but every read/write now flows through the Django backend.
// Nothing here touches localStorage anymore — HTTP is the only data path.
import { getCourses, getDepartments, getFaculties, getClasses, getMyEnrollments, enrollInCourse, dropFromCourse } from '../api/academic';
import { getSchoolYears, getSemesters, createSemester, updateSemester } from '../api/calendar';
import { getAnnouncements, createAnnouncement, updateAnnouncement } from '../api/announcements';
import {
  getProjects,
  createProject,
  updateProjectStatus,
  getProject,
  createTask,
  updateTaskStatus,
  createGroup,
  addMember,
} from '../api/projects';
import {
  listSessions,
  startSession,
  getSessionDetail,
  closeSession,
  selectCheckpoints,
  issueCheckpointToken,
  listRecords,
  submitCorrection,
  listReviewFlags,
  scanAttendance,
} from '../api/attendance';
import { getNotifications, markNotificationRead, markAllNotificationsRead } from '../api/notifications';
import { getStudents } from '../api/users';
import apiClient from '../api/client';
import {
  mapAll,
  mapAnnouncement,
  mapClassSession,
  mapCourse,
  mapGroup,
  mapMembership,
  mapMilestone,
  mapProject,
  mapSemester,
  mapSchoolYear,
  mapTask,
  mapAttendanceRecord,
  mapAttendanceSession,
} from '../utils/mappers';

const AppContext = createContext(null);

/** Academic = lecturer or admin. Mirrors core.academic_access.is_authorized_academic_user. */
const isAcademicRole = (role) =>
  String(role || '').toUpperCase() === 'LECTURER' || String(role || '').toUpperCase() === 'ADMINISTRATOR';
const isAdminRole = (role) => String(role || '').toUpperCase() === 'ADMINISTRATOR';

/**
 * Milestone endpoints. These live here rather than in api/projects.js because
 * the project api module predates them; consolidating is tracked separately.
 */
async function listMilestones(projectId) {
  const response = await apiClient.get(`/projects/${projectId}/milestones/`);
  return response.data;
}
async function createMilestone(projectId, payload) {
  const response = await apiClient.post(`/projects/${projectId}/milestones/`, payload);
  return response.data;
}
async function updateMilestoneApi(id, payload) {
  const response = await apiClient.patch(`/projects/milestones/${id}/`, payload);
  return response.data;
}
async function deleteMilestoneApi(id) {
  const response = await apiClient.delete(`/projects/milestones/${id}/`);
  return response.data;
}

export const AppProvider = ({ children, user }) => {
  const backendRole = user?.role;
  const academic = isAcademicRole(backendRole);
  const admin = isAdminRole(backendRole);

  // ===== Reference data =====
  const [schoolYears, setSchoolYears] = useState([]);
  const [semesters, setSemesters] = useState([]);
  const [courses, setCourses] = useState([]);
  const [departments, setDepartments] = useState([]);
  const [faculties, setFaculties] = useState([]);
  const [classSessions, setClassSessions] = useState([]);
  const [enrollments, setEnrollments] = useState([]);
  const [students, setStudents] = useState([]);
  const [lecturers, setLecturers] = useState([]); // backend has no lecturer-list endpoint
  const [announcements, setAnnouncements] = useState([]);

  // ===== Projects domain =====
  const [projects, setProjects] = useState([]);
  const [groups, setGroups] = useState([]);
  const [tasks, setTasks] = useState([]);
  const [milestones, setMilestones] = useState([]);
  const [memberships, setMemberships] = useState([]);

  // ===== Attendance domain =====
  const [attendanceSessions, setAttendanceSessions] = useState([]);
  const [attendanceRecords, setAttendanceRecords] = useState([]);
  const [attendance, setAttendance] = useState([]);

  // ===== UI-ish state =====
  const [activities, setActivities] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);

  const addActivity = useCallback((actor, action) => {
    setActivities((prev) =>
      [{ id: Date.now() + Math.random(), user: actor, action, time: new Date().toISOString() }, ...prev].slice(0, 50)
    );
  }, []);

  // ===== The one load path — everything hydrates from the backend =====
  const reload = useCallback(async () => {
    setLoading(true);
    setError(null);

    // Baseline every authenticated user may read.
    const jobs = [
      ['courses', getCourses, (v) => setCourses(mapAll(v, mapCourse))],
      ['semesters', getSemesters, (v) => setSemesters(mapAll(v, mapSemester))],
      ['schoolYears', getSchoolYears, (v) => setSchoolYears(mapAll(v, mapSchoolYear))],
      ['classSessions', getClasses, (v) => setClassSessions(mapAll(v, mapClassSession))],
      ['announcements', getAnnouncements, (v) => setAnnouncements(mapAll(v, mapAnnouncement))],
      ['projects', getProjects, (v) => setProjects(mapAll(v, mapProject))],
      ['attendanceRecords', listRecords, (v) => setAttendanceRecords(mapAll(v, mapAttendanceRecord))],
      ['enrollments', getMyEnrollments, (v) => setEnrollments(v || [])],
    ];

    // ACADEMIC-ONLY (C1): a student receives 403 for these. Calling them for a
    // student produced silent empty arrays, so they are gated on role.
    if (academic) {
      jobs.push(
        ['departments', getDepartments, (v) => setDepartments(v || [])],
        ['faculties', getFaculties, (v) => setFaculties(v || [])],
        ['students', getStudents, (v) => setStudents(v || [])],
        ['attendanceSessions', listSessions, (v) => setAttendanceSessions(mapAll(v, mapAttendanceSession))]
      );
    } else {
      setDepartments([]);
      setFaculties([]);
      setStudents([]);
      setAttendanceSessions([]);
    }

    const results = await Promise.allSettled(jobs.map(([, fn]) => fn()));
    const failures = [];
    results.forEach((result, index) => {
      const [name] = jobs[index];
      if (result.status === 'rejected') failures.push(`${name}: ${result.reason?.message || result.reason}`);
    });

    // Derived history rows (used by dashboards that render a legacy shape).
    setAttendance(
      (results[6].status === 'fulfilled' ? results[6].value : []) || []
    );

    // Detail bundles per project for groups/tasks/milestones/memberships.
    const projectList = results[5].status === 'fulfilled' ? results[5].value || [] : [];
    if (projectList.length > 0) {
      const details = await Promise.allSettled(projectList.map((p) => getProject(p.id)));
      const rows = details.filter((d) => d.status === 'fulfilled').map((d) => d.value);
      setGroups(rows.flatMap((d) => mapAll(d.groups, mapGroup)));
      setTasks(rows.flatMap((d) => mapAll(d.tasks, mapTask)));
      setMilestones(rows.flatMap((d) => mapAll(d.milestones, mapMilestone)));
      setMemberships(rows.flatMap((d) => mapAll(d.members, mapMembership)));
    } else {
      setGroups([]);
      setTasks([]);
      setMilestones([]);
      setMemberships([]);
    }

    // C1: surface partial failure instead of silently rendering empty lists.
    if (failures.length > 0) {
      setError(`Could not load: ${failures.join('; ')}`);
    }
    setLoading(false);
  }, [academic]);

  useEffect(() => {
    reload();
  }, [reload]);

  // ===== Derived values =====
  const currentSchoolYear = schoolYears.find((y) => y.isActive) || schoolYears[0] || null;
  const currentSemester = semesters.find((s) => s.isCurrent) || semesters[0] || null;

  // ===== Mutation helpers (each hits the API, then refetches) =====

  async function mutate(fn, onDone) {
    const result = await fn();
    await reload();
    if (onDone) onDone(result);
    return result;
  }

  // ===== Calendar (H3/H4: real snake_case contract) =====
  const addSemester = (data) =>
    mutate(() =>
      createSemester({
        school_year: data.schoolYearId || data.school_year,
        name: data.name,
        start_date: data.startDate || data.start_date,
        end_date: data.endDate || data.end_date,
        is_current: data.isCurrent ?? data.is_current ?? false,
      })
    );
  const updateSemesterAction = (id, updates) =>
    mutate(() =>
      updateSemester(id, {
        ...(updates.name !== undefined ? { name: updates.name } : {}),
        ...(updates.startDate !== undefined ? { start_date: updates.startDate } : {}),
        ...(updates.endDate !== undefined ? { end_date: updates.endDate } : {}),
        ...(updates.isCurrent !== undefined ? { is_current: updates.isCurrent } : {}),
      })
    );
  const switchSemester = (id) => mutate(() => updateSemester(id, { is_current: true }));

  // H4: the backend exposes NO DELETE for school-years or semesters, and
  // SchoolYear has no is_active field at all. These previously resolved silently,
  // so the buttons looked live but did nothing. They now REJECT LOUDLY, and the
  // corresponding UI controls were removed in SchoolYearManager/SemesterSelector.
  const unsupported = (what) =>
    Promise.reject(new Error(`${what} is not supported by the API. The control has been removed.`));
  const updateSchoolYear = () => unsupported('Updating a school year');
  const deleteSchoolYear = () => unsupported('Deleting a school year');
  const switchSchoolYear = () => unsupported('Switching the current school year');
  const deleteSemester = () => unsupported('Deleting a semester');

  // ===== Projects =====
  const addProject = (data) =>
    mutate(() => createProject({ title: data.title }), (p) => addActivity('System', `created project "${p.title}"`));
  const updateProject = (id, updates) =>
    mutate(
      () =>
        updates.status
          ? updateProjectStatus(id, updates.status)
          : Promise.reject(new Error('Only status updates are supported by the API')),
      () => addActivity('System', 'updated project')
    );
  const deleteProject = () => unsupported('Deleting a project');

  // H5: `assignee` is a user UUID on ProjectTask, not a matricule. The old code
  // sent data.assignedTo straight through, which could never resolve.
  const addTask = (data) =>
    mutate(
      () =>
        createTask(data.projectId || data.project, {
          title: data.title,
          ...(data.assignee ? { assignee: data.assignee } : {}),
          ...(data.status ? { status: data.status } : {}),
        }),
      (t) => addActivity('System', `created task "${t.title}"`)
    );
  const updateTask = (id, updates) =>
    mutate(
      () => (updates.status ? updateTaskStatus(id, updates.status) : Promise.reject(new Error('Only status updates supported'))),
      () => addActivity('System', 'updated task')
    );
  const deleteTask = () => unsupported('Deleting a task');

  const addGroup = (data) =>
    mutate(
      () => createGroup(data.projectId || data.project, { name: data.name }),
      (g) => addActivity('System', `created group "${g.name}"`)
    );
  const updateGroup = () => unsupported('Updating a group');
  const deleteGroup = () => unsupported('Deleting a group');

  // ===== Milestones (the one place dueDate is a real field) =====
  const addMilestone = (data) =>
    mutate(
      () =>
        createMilestone(data.projectId || data.project, {
          title: data.title,
          progress: data.progress ?? 0,
          due_date: data.dueDate || data.due_date || null,
        }),
      (m) => addActivity('System', `created milestone "${m.title}"`)
    );
  const updateMilestone = (id, updates) =>
    mutate(
      () =>
        updateMilestoneApi(id, {
          ...(updates.title !== undefined ? { title: updates.title } : {}),
          ...(updates.progress !== undefined ? { progress: updates.progress } : {}),
          ...(updates.dueDate !== undefined ? { due_date: updates.dueDate } : {}),
        }),
      () => addActivity('System', 'updated milestone')
    );
  const deleteMilestone = (id) => mutate(() => deleteMilestoneApi(id), () => addActivity('System', 'deleted milestone'));

  // ===== Announcements (H1/H2: real serializer contract) =====
  const addAnnouncement = (data) =>
    mutate(
      () =>
        createAnnouncement({
          title: data.title,
          body: data.content || data.body,
          scope: data.scope,
          scope_id: data.scopeId || data.scope_id, // REQUIRED by the backend
          is_important: data.isImportant ?? data.is_important ?? false,
          published: data.published ?? true,
        }),
      (a) => addActivity('System', `posted announcement "${a.title}"`)
    );
  const updateAnnouncementAction = (id, updates) =>
    mutate(
      () =>
        updateAnnouncement(id, {
          ...(updates.title !== undefined ? { title: updates.title } : {}),
          ...(updates.content !== undefined ? { body: updates.content } : {}),
          ...(updates.body !== undefined ? { body: updates.body } : {}),
          ...(updates.isImportant !== undefined ? { is_important: updates.isImportant } : {}),
          ...(updates.published !== undefined ? { published: updates.published } : {}),
        }),
      () => addActivity('System', 'updated announcement')
    );
  const deleteAnnouncement = () => unsupported('Deleting an announcement');

  // ===== Attendance =====
  const addAttendanceSession = (data) =>
    mutate(() => startSession(data.classSessionId || data.class_session, data.duration_seconds || data.duration));
  const closeAttendanceSession = (sessionId) => mutate(() => closeSession(sessionId));
  const recordAttendance = async (sessionToken) => {
    // The backend accepts only a token minted for THIS student (BR-039); a
    // session id is never redeemable.
    const result = await scanAttendance(sessionToken);
    await reload();
    return { success: true, record: result };
  };
  const updateSessionToken = () => unsupported('Client-side token rotation');
  const selectCheckpointsForSession = (sessionId, studentIds) => mutate(() => selectCheckpoints(sessionId, studentIds));
  const requestCheckpointToken = (checkpointId) => issueCheckpointToken(checkpointId);

  const getActiveSession = () => attendanceSessions.find((s) => s.status === 'ACTIVE') || null;
  const getAttendanceForSession = (sessionId) =>
    attendanceRecords.filter((r) => String(r.attendance_session) === String(sessionId));
  const updateAttendanceRecord = (recordId, updates) =>
    updates?.reason ? mutate(() => submitCorrection(recordId, updates.reason)) : Promise.resolve();

  // ===== Enrollment (M3) — the real server-side action =====
  // Previously the Enrol/Drop button wrote to localStorage, which created no
  // Enrollment row and therefore had no effect on attendance eligibility.
  const enroll = (courseId) => mutate(() => enrollInCourse(courseId));
  const drop = (courseId) => mutate(() => dropFromCourse(courseId));

  // ===== Directory =====
  const getCoursesForStudent = () => courses;
  const getCurrentSemesterStats = () => ({
    semester: currentSemester,
    schoolYear: currentSchoolYear,
    attendance: attendanceRecords.length ? 100 : 0,
    totalClasses: attendanceRecords.length,
    present: attendanceRecords.filter((r) => r.status === 'PRESENT').length,
    absent: 0,
  });

  // C1: student provisioning is registration-only; these now fail loudly with
  // the real reason instead of a canned string.
  const addStudent = () =>
    Promise.reject(new Error('Students register through /accounts/register/ or are provisioned by an administrator.'));
  const updateStudent = () => Promise.reject(new Error('Student profiles are edited via PATCH /accounts/me/.'));
  const addLecturer = () => Promise.reject(new Error('Lecturers are provisioned by an administrator.'));
  const updateLecturer = () => Promise.reject(new Error('Lecturer profiles are edited via PATCH /accounts/me/.'));

  const getNotificationsList = () => getNotifications();
  const markRead = (id) => markNotificationRead(id);
  const markAllRead = () => markAllNotificationsRead();
  const listReviewFlagsApi = () => listReviewFlags();
  const correctRecord = (recordId, reason) => submitCorrection(recordId, reason);

  const value = useMemo(
    () => ({
      // state
      schoolYears, semesters, courses, departments, faculties, classSessions,
      students, lecturers, announcements,
      projects, groups, tasks, milestones, memberships,
      attendanceSessions, attendanceRecords, attendance, activities, enrollments,
      loading, error, currentSchoolYear, currentSemester,
      // calendar
      addSchoolYear: () => unsupported('Creating a school year'),
      updateSchoolYear, deleteSchoolYear, switchSchoolYear,
      addSemester, updateSemester: updateSemesterAction, deleteSemester, switchSemester,
      // projects
      addProject, updateProject, deleteProject,
      addTask, updateTask, deleteTask,
      addGroup, updateGroup, deleteGroup,
      addMilestone, updateMilestone, deleteMilestone,
      // announcements
      addAnnouncement, updateAnnouncement: updateAnnouncementAction, deleteAnnouncement,
      // attendance
      addAttendanceSession, updateSessionToken, closeAttendanceSession,
      selectCheckpoints: selectCheckpointsForSession,
      requestCheckpointToken,
      getActiveSession, getAttendanceForSession, updateAttendanceRecord, recordAttendance,
      listReviewFlags: listReviewFlagsApi, correctRecord,
      getSessionDetail,
      // directory
      addStudent, updateStudent, addLecturer, updateLecturer,
      getCoursesForStudent, getCurrentSemesterStats, addActivity,
      // enrollment
      enroll, drop,
      // notifications
      getNotificationsList, markRead, markAllRead,
      // capability flags so UI can hide controls the API cannot honour
      capabilities: { academic, admin },
    }),
    [
      schoolYears, semesters, courses, departments, faculties, classSessions,
      students, lecturers, announcements, projects, groups, tasks, milestones,
      memberships, attendanceSessions, attendanceRecords, attendance, activities,
      enrollments, loading, error, currentSchoolYear, currentSemester,
      academic, admin,
    ]
  );

  return <AppContext.Provider value={value}>{children}</AppContext.Provider>;
};

export const useAppContext = () => {
  const context = useContext(AppContext);
  if (!context) throw new Error('useAppContext must be used within AppProvider');
  return context;
};
