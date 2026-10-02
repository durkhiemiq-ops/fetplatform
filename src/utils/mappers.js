/**
 * Central response mappers — snake_case → the camelCase shape Attendî's
 * components already consume.
 *
 * These are the ONLY place the backend's wire format is translated. Components
 * never read snake_case keys, and the backend is never asked to emit camelCase
 * (that would put one client's conventions in the server).
 *
 * @module utils/mappers
 */

/** SchoolYear has no is_active field on the model (verified against
 *  GET /api/v1/academic/school-years/). We derive nothing — callers must treat
 *  `isActive` as absent rather than assume a current year. */
export function mapSchoolYear(row) {
  if (!row) return null;
  return {
    ...row,
    startDate: row.start_date ?? null,
    endDate: row.end_date ?? null,
    isActive: row.is_active ?? false,
  };
}

/** Semester DOES have is_current on the model. */
export function mapSemester(row) {
  if (!row) return null;
  return {
    ...row,
    startDate: row.start_date ?? null,
    endDate: row.end_date ?? null,
    isCurrent: row.is_current === true,
    isActive: row.is_active ?? true,
    schoolYear: row.school_year_name ?? null,
    schoolYearId: row.school_year ?? null,
  };
}

export function mapCourse(row) {
  if (!row) return null;
  return {
    ...row,
    departmentName: row.department_name ?? null,
    facultyName: row.faculty_name ?? null,
  };
}

export function mapClassSession(row) {
  if (!row) return null;
  return {
    ...row,
    courseCode: row.course_code ?? null,
    lecturerName: row.lecturer_name ?? null,
    startsAt: row.starts_at ?? null,
  };
}

/**
 * Announcement. Backend fields: id, title, body, scope, scope_label, faculty,
 * department, course, class_session, is_published, is_important, published_at,
 * created_by, created_at.
 *
 * The old mock shape had `type` / `date` / `author` / `content` — those do not
 * exist server-side. `type` is derived from is_important + publication state;
 * `author` is deliberately NOT synthesised from created_by because that is a
 * bare UUID, not a name. Resolve the name upstream if one is genuinely needed.
 */
export function mapAnnouncement(row) {
  if (!row) return null;
  const type = row.is_important ? 'Important' : (row.is_published ? 'Update' : 'Draft');
  return {
    ...row,
    content: row.body ?? '',
    type,
    date: row.published_at || row.created_at || null,
    author: null, // UUID upstream — see note above
    scopeLabel: row.scope_label ?? row.scope ?? null,
  };
}

/**
 * Project. Backend has NO progress and NO deadline columns. We do not fabricate
 * them here — see mapProjectProgress for the milestone-derived value.
 */
export function mapProject(row) {
  if (!row) return null;
  return {
    ...row,
    ownerName: row.owner_name ?? null,
    supervisorName: row.supervisor_name ?? null,
  };
}

/** ProjectTask. Backend has NO dueDate column. `assignee` is a user UUID. */
export function mapTask(row) {
  if (!row) return null;
  return {
    ...row,
    assigneeName: row.assignee_name ?? null,
    assignee: row.assignee ?? null,
    assignedTo: row.assignee ?? null, // UUID — compare against user.id, not matricule
    dueDate: null, // no such column on ProjectTask
    dueDateAvailable: false,
  };
}

/** ProjectMilestone DOES have due_date. This is the one real exception. */
export function mapMilestone(row) {
  if (!row) return null;
  return {
    ...row,
    dueDate: row.due_date ?? null,
    projectId: row.project ?? null,
  };
}

/** ProjectGroup. MembershipSerializer uses `group`, not `projectId`. */
export function mapGroup(row) {
  if (!row) return null;
  return {
    ...row,
    projectId: row.project ?? null,
    leaderName: row.leader_name ?? null,
  };
}

export function mapMembership(row) {
  if (!row) return null;
  return {
    ...row,
    projectId: row.project ?? null,
    groupId: row.group ?? null,
    studentId: row.student ?? null,
    studentName: row.student_name ?? null,
  };
}

/** Attendance record row from GET /attendance/records/. */
export function mapAttendanceRecord(row) {
  if (!row) return null;
  return {
    ...row,
    courseCode: row.course_code ?? null,
    courseName: row.course_name ?? null,
    studentName: row.student_name ?? null,
    recordedAt: row.recorded_at ?? null,
    time: row.recorded_at ?? null,
    date: row.recorded_at ? String(row.recorded_at).split('T')[0] : null,
  };
}

/** Attendance session row from GET /attendance/sessions/. */
export function mapAttendanceSession(row) {
  if (!row) return null;
  return {
    ...row,
    courseCode: row.course_code ?? null,
    courseName: row.course_name ?? null,
    startedAt: row.started_at ?? null,
    expiresAt: row.expires_at ?? null,
  };
}

/**
 * Task status vocabulary. Backend stores todo | in_progress | completed;
 * the UI previously rendered "To do" | "In Progress" | "Completed".
 * One place, both directions.
 */
export const TASK_STATUS_LABELS = {
  todo: 'To do',
  in_progress: 'In Progress',
  completed: 'Completed',
};

export function taskStatusLabel(value) {
  if (!value) return '';
  return TASK_STATUS_LABELS[value] || value;
}

/** Map an array of rows through a mapper, dropping nulls. */
export function mapAll(rows, mapper) {
  if (!Array.isArray(rows)) return [];
  return rows.map(mapper).filter(Boolean);
}
