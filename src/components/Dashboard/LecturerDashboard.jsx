import React, { useState, useEffect } from 'react';
import { 
  Users, FolderKanban, CheckCircle, Clock, 
  BookOpen, AlertCircle, QrCode, Search
} from 'lucide-react';
import { useNavigate } from 'react-router-dom';
import StatsCard from './StatsCard';
import ActivityFeed from './ActivityFeed';
import { useAppContext } from '../../context/AppContext';

const LecturerDashboard = ({ user }) => {
  const navigate = useNavigate();
  const { students, projects, tasks, attendanceRecords, classSessions } = useAppContext();
  const [stats, setStats] = useState({ 
    enrolled: 0,
    present: 0,
    late: 0,
    notCheckedIn: 0,
    courses: 0,
    projects: 0,
    pending: 0,
  });
  const [reviewRows, setReviewRows] = useState([]);
  const [searchTerm, setSearchTerm] = useState('');

  const lecturerName = user?.fullName || 'Lecturer';
  const lecturerDepartment = user?.department || 'Engineering';
  const lecturerTitle = user?.title || 'Lecturer';

  useEffect(() => {
    // H5: attendance records use `status: 'PRESENT'` and carry `student_name`
    // directly; the old code filtered on 'Present'/'Late'/'Review' and joined to
    // a student by a matricule that the record does not carry.
    const present = attendanceRecords.filter((a) => a.status === 'PRESENT').length;
    const notCheckedIn = Math.max(0, students.length - present);

    setStats({
      enrolled: students.length,
      present,
      late: 0, // the backend has no LATE status; see mappers.mapAttendanceRecord
      notCheckedIn,
      courses: classSessions.length,
      projects: projects.filter(
        (p) => p.supervisor === user?.id || p.owner === user?.id || p.supervisorName === lecturerName
      ).length,
      pending: tasks.filter((t) => t.status !== 'completed').length,
    });

    setReviewRows(
      attendanceRecords
        .filter((r) => r.corrected)
        .map((r) => ({ fullName: r.student_name || r.studentName || '—', id: r.id, status: 'Corrected' }))
    );
  }, [students, attendanceRecords, projects, tasks, classSessions, user, lecturerName]);

  const statCards = [
    { icon: Users, label: 'Total Students', value: stats.enrolled, color: 'secondary' },
    { icon: CheckCircle, label: 'Present Today', value: stats.present, color: 'success' },
    { icon: Clock, label: 'Late Arrivals', value: stats.late, color: 'warning' },
    { icon: AlertCircle, label: 'Absent', value: stats.notCheckedIn, color: 'error' },
  ];

  const filteredReviewRows = reviewRows.filter(s =>
    s.fullName.toLowerCase().includes(searchTerm.toLowerCase()) ||
    s.id.toLowerCase().includes(searchTerm.toLowerCase())
  );

  return (
    <div className="space-y-5 max-w-7xl mx-auto">
      {/* Welcome Banner */}
      <div className="fet-welcome-banner">
        <div className="relative z-10 flex flex-col sm:flex-row items-start sm:items-center justify-between gap-4">
          <div>
            <h2 className="text-[20px] md:text-[22px] font-bold">Welcome back, {lecturerName}</h2>
            <p className="text-white/50 text-[13px]">{lecturerTitle} · {lecturerDepartment} Department</p>
            <p className="text-white/35 text-[12px] mt-0.5">Teaching {stats.courses} courses this semester</p>
          </div>
          <div className="bg-white/10 backdrop-blur-sm rounded-xl px-5 py-3 text-center min-w-[100px] border border-white/10">
            <p className="text-[11px] text-white/50 font-medium uppercase tracking-wider">Students</p>
            <p className="text-[26px] font-bold text-white leading-tight">{stats.enrolled}</p>
          </div>
        </div>
      </div>

      {/* Stats Cards */}
      <div className="grid grid-cols-2 lg:grid-cols-4 gap-3 md:gap-4">
        {statCards.map((stat, index) => (
          <StatsCard key={index} {...stat} />
        ))}
      </div>

      {/* QR Section + Review */}
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-4 md:gap-5">
        <div className="lg:col-span-1">
          <div className="fet-card p-5">
            <h3 className="text-[15px] font-semibold text-text-primary mb-4">Quick Attendance</h3>
            <div className="p-6 rounded-xl text-center" style={{ backgroundColor: 'rgba(63,53,181,0.04)', border: '1px dashed rgba(63,53,181,0.2)' }}>
              <QrCode size={48} className="mx-auto text-primary" strokeWidth={1.5} />
              <p className="text-[13px] text-text-secondary mt-3">Generate a QR code for your next lecture</p>
              <button
                onClick={() => navigate('/attendance')}
                className="fet-btn-primary mt-4 px-6"
              >
                Generate QR
              </button>
            </div>
            <div className="mt-4 grid grid-cols-3 gap-2">
              <div className="text-center p-2.5 rounded-lg bg-page-bg">
                <p className="text-[18px] font-bold text-text-primary">{stats.enrolled}</p>
                <p className="text-[10px] text-text-secondary font-medium">Enrolled</p>
              </div>
              <div className="text-center p-2.5 rounded-lg bg-page-bg">
                <p className="text-[18px] font-bold text-success">{stats.present}</p>
                <p className="text-[10px] text-text-secondary font-medium">Present</p>
              </div>
              <div className="text-center p-2.5 rounded-lg bg-page-bg">
                <p className="text-[18px] font-bold text-danger">{stats.notCheckedIn}</p>
                <p className="text-[10px] text-text-secondary font-medium">Absent</p>
              </div>
            </div>
          </div>
        </div>

        <div className="lg:col-span-2">
          <div className="fet-card p-5">
            <div className="flex items-center justify-between mb-4">
              <h3 className="text-[15px] font-semibold text-text-primary flex items-center gap-2">
                <Users size={16} className="text-primary" strokeWidth={2} />
                Attendance Review
              </h3>
              {reviewRows.length > 0 && (
                <button onClick={() => navigate('/attendance')} className="text-[12px] text-primary font-semibold hover:opacity-80">
                  View All →
                </button>
              )}
            </div>
            <div className="relative mb-4">
              <Search className="absolute left-3 top-1/2 transform -translate-y-1/2 text-text-secondary" size={15} />
              <input
                type="text"
                placeholder="Search students..."
                value={searchTerm}
                onChange={(e) => setSearchTerm(e.target.value)}
                className="fet-input pl-9 pr-4 py-2 text-[13px]"
              />
            </div>
            {filteredReviewRows.length > 0 ? (
              <div className="overflow-x-auto">
                <table className="fet-table">
                  <thead>
                    <tr>
                      <th>Student</th>
                      <th>ID</th>
                      <th>Status</th>
                    </tr>
                  </thead>
                  <tbody>
                    {filteredReviewRows.map((s, i) => (
                      <tr key={i}>
                        <td className="font-medium">{s.fullName}</td>
                        <td className="text-text-secondary text-[12px]">{s.id}</td>
                        <td>
                          <span className="fet-badge fet-badge-review">{s.status}</span>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            ) : (
              <div className="text-center py-8">
                <CheckCircle size={32} className="mx-auto text-success/50" />
                <p className="text-[13px] text-text-secondary mt-2">No records requiring review</p>
                <p className="text-[11px] text-text-secondary">Start an attendance session to begin capturing student attendance.</p>
              </div>
            )}
          </div>
        </div>
      </div>

      {/* My Class Sessions */}
      <div className="fet-card p-5">
        <h3 className="text-[15px] font-semibold text-text-primary flex items-center gap-2 mb-4">
          <BookOpen size={16} className="text-primary" strokeWidth={2} />
          My Class Sessions ({classSessions.length})
        </h3>
        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-3">
          {classSessions.length > 0 ? (
            classSessions.map((cs) => (
              <div
                key={cs.id}
                className="flex items-center justify-between p-3.5 rounded-xl bg-page-bg border border-transparent hover:border-border-default transition-colors"
              >
                <div className="min-w-0">
                  <p className="font-semibold text-text-primary text-[13px]">
                    {cs.courseCode || '\u2014'}
                  </p>
                  <p className="text-[12px] text-text-secondary mt-0.5 truncate">
                    {cs.lecturerName || '\u2014'}
                  </p>
                </div>
                <div className="text-right flex-shrink-0 ml-2">
                  <p className="text-[11px] text-text-secondary">
                    {cs.startsAt ? new Date(cs.startsAt).toLocaleDateString() : '\u2014'}
                  </p>
                </div>
              </div>
            ))
          ) : (
            <p className="text-center text-text-secondary py-4 text-[13px] col-span-full">
              No class sessions assigned
            </p>
          )}
        </div>
      </div>
    </div>
  );
};

export default LecturerDashboard;
