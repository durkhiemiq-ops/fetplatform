import React, { useState, useEffect, useCallback } from 'react';
import { useNavigate } from 'react-router-dom';
import { CalendarDays, AlertCircle, RefreshCw, Settings } from 'lucide-react';
import { academicsApi } from '../../lib/academics';
import { errorMessage } from '../../lib/enrollment';
import { formatDate } from '../../lib/format';

/**
 * The active semester, read from the backend.
 *
 * This previously showed `currentSemester` / `currentSchoolYear` out of the
 * mock store, so it rendered a fixed invented period ("2025/2026 Semester 2")
 * regardless of what the database actually had. It also embedded
 * SemesterSelector and SchoolYearManager, which were mock editors with no
 * backend behind them; semester management now lives at /admin/academic.
 */
const AcademicCalendar = () => {
  const navigate = useNavigate();
  const [semesters, setSemesters] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');

  const load = useCallback(async () => {
    setLoading(true);
    setError('');
    try {
      setSemesters((await academicsApi.semesters()) || []);
    } catch (err) {
      setError(errorMessage(err, 'Could not load semesters.'));
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { load(); }, [load]);

  const active = semesters.find((s) => s.is_active) || null;

  const tiles = [
    { label: 'Semester', value: active ? active.name : 'None active' },
    { label: 'Academic year', value: active ? active.academic_year : '—' },
    { label: 'Starts', value: active ? formatDate(active.start_date) : '—' },
    { label: 'Ends', value: active ? formatDate(active.end_date) : '—' },
    {
      label: 'Registration closes',
      value: active && active.registration_deadline ? formatDate(active.registration_deadline) : 'Not set',
    },
  ];

  return (
    <div className="space-y-6">
      <div className="fet-welcome-banner">
        <div className="flex items-start justify-between gap-4 flex-wrap">
          <div>
            <h2 className="text-2xl font-bold">Academic Calendar</h2>
            {active ? (
              <>
                <p className="text-[#8683BA] mt-1">
                  {active.name} • {active.academic_year}
                </p>
                <p className="text-[#8683BA] text-sm mt-1">
                  {formatDate(active.start_date)} – {formatDate(active.end_date)}
                </p>
              </>
            ) : (
              <p className="text-[#8683BA] mt-1">
                No semester is active — registration and enrolment are closed.
              </p>
            )}
          </div>
          <div className="flex gap-2">
            <button type="button" onClick={load} className="fet-btn-secondary" disabled={loading}>
              <RefreshCw size={14} /> Refresh
            </button>
            <button type="button" onClick={() => navigate('/admin/academic')} className="fet-btn-primary">
              <Settings size={14} /> Manage
            </button>
          </div>
        </div>
      </div>

      {error ? (
        <div className="bg-red-50 border border-red-200 text-red-700 px-4 py-3 rounded-xl text-[13px] flex items-center gap-2">
          <AlertCircle size={16} /> {error}
        </div>
      ) : null}

      <div className="fet-card p-6">
        <h3 className="text-lg font-semibold text-text-primary mb-4" style={{ fontSize: '15px' }}>
          Current Semester Information
        </h3>
        <div className="grid grid-cols-2 md:grid-cols-5 gap-4">
          {tiles.map((t) => (
            <div key={t.label} className="p-3 bg-page-bg rounded-xl text-center">
              <p className="text-xs text-text-secondary">{t.label}</p>
              <p className="font-semibold text-text-primary text-[13px]">{t.value}</p>
            </div>
          ))}
        </div>
      </div>

      <div className="fet-card p-6">
        <h3 className="text-[15px] font-semibold text-text-primary mb-4">All Semesters</h3>
        {loading ? (
          <p className="text-center text-text-secondary py-6 text-[13px]">Loading semesters...</p>
        ) : semesters.length === 0 ? (
          <div className="text-center py-8">
            <CalendarDays size={30} className="mx-auto text-text-secondary/30" />
            <p className="text-[13px] text-text-secondary mt-2">No semesters defined yet</p>
          </div>
        ) : (
          <div className="overflow-x-auto">
            <table className="fet-table">
              <thead>
                <tr>
                  <th>Semester</th>
                  <th>Year</th>
                  <th>No.</th>
                  <th>Starts</th>
                  <th>Ends</th>
                  <th>Registration closes</th>
                  <th>State</th>
                </tr>
              </thead>
              <tbody>
                {semesters.map((s) => (
                  <tr key={s.id}>
                    <td className="font-medium">{s.name}</td>
                    <td>{s.academic_year}</td>
                    <td>{s.number}</td>
                    <td>{formatDate(s.start_date)}</td>
                    <td>{formatDate(s.end_date)}</td>
                    <td>{s.registration_deadline ? formatDate(s.registration_deadline) : '—'}</td>
                    <td>
                      {s.is_active
                        ? <span className="fet-badge fet-badge-active">Active</span>
                        : <span className="fet-badge fet-badge-inactive">{s.status}</span>}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>
    </div>
  );
};

export default AcademicCalendar;
