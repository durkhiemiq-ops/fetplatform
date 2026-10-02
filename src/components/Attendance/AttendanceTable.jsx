import React from 'react';

const AttendanceTable = ({ records }) => {
  if (!records || records.length === 0) {
    return (
      <div className="text-center py-8 text-text-secondary">
        No attendance records for this session
      </div>
    );
  }

  return (
    <div className="overflow-x-auto">
      <table className="fet-table">
        <thead>
          <tr>
            <th>Student</th>
            <th>ID</th>
            <th>Status</th>
            <th>Time</th>
            <th>Method</th>
          </tr>
        </thead>
        <tbody>
          {records.map((record) => (
            <tr key={record.id}>
              <td className="font-medium">{record.studentName || record.studentId}</td>
              <td className="text-sm">{record.studentId}</td>
              <td>
                <span className={`fet-badge ${
                  record.status === 'PRESENT' ? 'fet-badge-present' : 'fet-badge-absent'
                }`}>
                  {record.status}
                </span>
              </td>
              <td className="text-sm">{record.time}</td>
              <td className="text-sm">{record.method}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
};

export default AttendanceTable;
