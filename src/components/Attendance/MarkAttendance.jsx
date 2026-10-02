import React, { useState } from 'react';

const MarkAttendance = ({ students, onSubmit, onCancel }) => {
  const [formData, setFormData] = useState({
    studentId: '',
    course: 'Data Structures 101',
    status: 'Present',
  });

  const handleSubmit = (e) => {
    e.preventDefault();
    const student = students.find(s => s.id === formData.studentId);
    if (student) {
      onSubmit({
        ...formData,
        studentName: student.name,
      });
    }
  };

  return (
    <form onSubmit={handleSubmit} className="space-y-4">
      <div>
        <label className="fet-label">Student</label>
        <select
          value={formData.studentId}
          onChange={(e) => setFormData(prev => ({ ...prev, studentId: e.target.value }))}
          required
          className="fet-select"
        >
          <option value="">Select Student</option>
          {students.map(s => (
            <option key={s.id} value={s.id}>{s.name} ({s.id})</option>
          ))}
        </select>
      </div>

      <div>
        <label className="fet-label">Course</label>
        <input
          type="text"
          value={formData.course}
          onChange={(e) => setFormData(prev => ({ ...prev, course: e.target.value }))}
          className="fet-input"
        />
      </div>

      <div>
        <label className="fet-label">Status</label>
        <select
          value={formData.status}
          onChange={(e) => setFormData(prev => ({ ...prev, status: e.target.value }))}
          className="fet-select"
        >
          <option value="Present">Present</option>
          <option value="Late">Late</option>
          <option value="Absent">Absent</option>
          <option value="Review">Review</option>
        </select>
      </div>

      <div className="flex justify-end gap-3 pt-4 border-t border-border-default">
        <button
          type="button"
          onClick={onCancel}
          className="fet-btn-secondary"
        >
          Cancel
        </button>
        <button
          type="submit"
          className="fet-btn-primary"
        >
          Mark Attendance
        </button>
      </div>
    </form>
  );
};

export default MarkAttendance;