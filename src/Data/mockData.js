// Deprecated: the app no longer reads from localStorage-backed mock data.
// All data flows through the Django REST API via src/api/*. Keep this file
// only so existing imports don't break while the migration completes.

export const mockSchoolYears = [];
export const mockSemesters = [];
export const mockStudents = [];
export const mockLecturers = [];
export const mockCourses = [];
export const mockAnnouncements = [];
export const mockProjects = [];
export const mockGroups = [];
export const mockTasks = [];
export const mockMilestones = [];
export const mockAttendance = [];
export const mockAttendanceSessions = [];
export const mockAttendanceRecords = [];
export const mockAdmin = null;

export const getCurrentSchoolYear = () => ({ name: '', isActive: false });
export const getCurrentSemester = () => ({ name: '', isCurrent: false });
export const getStudentAttendance = () => [];
export const getStudentAttendancePercentage = () => 0;
