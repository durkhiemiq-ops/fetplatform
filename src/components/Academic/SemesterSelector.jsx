import React, { useState } from 'react';
import { useAppContext } from '../../context/AppContext';
import { Calendar, Plus, X, Save, Check, Info } from 'lucide-react';

/**
 * SemesterSelector — create/update semesters through the real contract.
 *
 * H3/H4 fixes:
 *  - `is_current` / `start_date` / `end_date` / `school_year` are the backend
 *    field names. The old form sent camelCase plus a `schoolYear` NAME where the
 *    API requires a UUID, so every create was rejected.
 *  - `isCurrent` is real on the model, so "switch current" is kept (PATCH
 *    /academic/semesters/{id}/ with {is_current:true} demotes the previous one
 *    server-side).
 *  - DELETE is NOT exposed by the API, so the delete control is removed instead
 *    of being a button that silently resolves to nothing.
 *  - `shortName` does not exist on the model; it is removed.
 */
const SemesterSelector = () => {
  const { semesters, schoolYears, addSemester, updateSemester, switchSemester, capabilities } = useAppContext();
  const [showForm, setShowForm] = useState(false);
  const [editingId, setEditingId] = useState(null);
  const [error, setError] = useState('');
  const [busy, setBusy] = useState(false);
  const [formData, setFormData] = useState({
    name: 'First Semester',
    schoolYearId: '',
    startDate: '',
    endDate: '',
    isCurrent: false,
  });

  // Writes are admin-only server-side; hide the controls from non-admins.
  const canWrite = capabilities?.admin;

  const resetForm = () =>
    setFormData({ name: 'First Semester', schoolYearId: schoolYears[0]?.id || '', startDate: '', endDate: '', isCurrent: false });

  const handleSubmit = async (e) => {
    e.preventDefault();
    setError('');
    if (!formData.name || !formData.schoolYearId || !formData.startDate || !formData.endDate) {
      setError('All fields are required.');
      return;
    }
    setBusy(true);
    try {
      if (editingId) {
        await updateSemester(editingId, {
          name: formData.name,
          startDate: formData.startDate,
          endDate: formData.endDate,
          isCurrent: formData.isCurrent,
        });
      } else {
        await addSemester(formData);
      }
      setEditingId(null);
      resetForm();
      setShowForm(false);
    } catch (err) {
      setError(err.message || 'Could not save the semester.');
    } finally {
      setBusy(false);
    }
  };

  const handleEdit = (semester) => {
    setEditingId(semester.id);
    setFormData({
      name: semester.name,
      schoolYearId: semester.schoolYearId || '',
      startDate: semester.startDate || '',
      endDate: semester.endDate || '',
      isCurrent: semester.isCurrent,
    });
    setError('');
    setShowForm(true);
  };

  const handleCancel = () => {
    resetForm();
    setEditingId(null);
    setError('');
    setShowForm(false);
  };

  const getStatusColor = (semester) =>
    semester.isCurrent ? 'fet-badge fet-badge-active' : 'fet-badge fet-badge-inactive';

  return (
    <div className="fet-card p-6">
      <div className="flex items-center justify-between mb-4">
        <h3 className="text-lg font-semibold text-text-primary flex items-center gap-2" style={{ fontSize: '15px' }}>
          <Calendar size={20} className="text-primary" />
          Semesters
        </h3>
        {canWrite && (
          <button onClick={() => { resetForm(); setShowForm(true); }} className="flex items-center gap-1 text-sm text-primary hover:underline">
            <Plus size={16} />
            Add Semester
          </button>
        )}
      </div>

      {!canWrite && (
        <p className="mb-3 flex items-start gap-1.5 text-[11px] text-text-secondary">
          <Info size={12} className="mt-0.5 flex-shrink-0" />
          Only administrators may create or change semesters.
        </p>
      )}

      <div className="space-y-2">
        {semesters.length === 0 ? (
          <p className="text-sm text-text-secondary py-4 text-center">No semesters available.</p>
        ) : (
          semesters.map((semester) => (
            <div
              key={semester.id}
              className={`flex items-center justify-between p-3 rounded-xl transition-colors ${
                semester.isCurrent ? 'bg-primary/10 border-2 border-primary' : 'bg-page-bg border border-border-default'
              }`}
            >
              <div>
                <div className="flex items-center gap-2">
                  <p className="font-medium text-text-primary">{semester.name}</p>
                  <span className={getStatusColor(semester)}>
                    {semester.isCurrent ? 'Current' : 'Past'}
                  </span>
                </div>
                <p className="text-xs text-text-secondary">
                  {semester.schoolYear || '—'} • {semester.startDate || '—'} – {semester.endDate || '—'}
                </p>
              </div>
              {canWrite && (
                <div className="flex items-center gap-2">
                  <button
                    onClick={() => handleEdit(semester)}
                    className="px-3 py-1 text-xs text-primary hover:underline"
                    aria-label={`Edit ${semester.name}`}
                  >
                    Edit
                  </button>
                  <button
                    onClick={() => switchSemester(semester.id)}
                    className={`px-3 py-1 text-xs rounded-lg transition-colors ${
                      semester.isCurrent ? 'fet-btn-success cursor-default' : 'fet-btn-primary'
                    }`}
                    disabled={semester.isCurrent}
                  >
                    {semester.isCurrent ? <><Check size={12} /> Current</> : 'Make current'}
                  </button>
                </div>
              )}
            </div>
          ))
        )}
      </div>

      {showForm && canWrite && (
        <form onSubmit={handleSubmit} className="mt-4 p-4 border border-border-default rounded-xl">
          <div className="flex items-center justify-between mb-3">
            <h4 className="font-medium text-text-primary">{editingId ? 'Edit Semester' : 'Add Semester'}</h4>
            <button type="button" onClick={handleCancel} className="text-text-secondary hover:text-text-primary">
              <X size={18} />
            </button>
          </div>

          {error && (
            <div className="mb-3 rounded-lg border border-red-200 bg-red-50 px-3 py-2 text-[13px] text-red-700">
              {error}
            </div>
          )}

          <div className="grid grid-cols-2 gap-3">
            <div>
              <label className="fet-label">Semester Name</label>
              <select
                value={formData.name}
                onChange={(e) => setFormData({ ...formData, name: e.target.value })}
                className="w-full px-3 py-2 fet-select"
                required
              >
                <option value="First Semester">First Semester</option>
                <option value="Second Semester">Second Semester</option>
              </select>
            </div>
            <div>
              <label className="fet-label">School Year</label>
              <select
                value={formData.schoolYearId}
                onChange={(e) => setFormData({ ...formData, schoolYearId: e.target.value })}
                className="w-full px-3 py-2 fet-select"
                required
              >
                <option value="">Select school year…</option>
                {schoolYears.map((year) => (
                  <option key={year.id} value={year.id}>{year.name}</option>
                ))}
              </select>
            </div>
            <div>
              <label className="fet-label">Start Date</label>
              <input
                type="date"
                value={formData.startDate}
                onChange={(e) => setFormData({ ...formData, startDate: e.target.value })}
                className="w-full px-3 py-2 fet-input"
                required
              />
            </div>
            <div>
              <label className="fet-label">End Date</label>
              <input
                type="date"
                value={formData.endDate}
                onChange={(e) => setFormData({ ...formData, endDate: e.target.value })}
                className="w-full px-3 py-2 fet-input"
                required
              />
            </div>
          </div>

          {!editingId && (
            <div className="mt-3 flex items-center gap-2">
              <input
                id="semester-current"
                type="checkbox"
                checked={formData.isCurrent}
                onChange={(e) => setFormData({ ...formData, isCurrent: e.target.checked })}
                className="w-4 h-4 rounded accent-primary"
              />
              <label htmlFor="semester-current" className="text-[13px] text-text-primary">
                Make this the current semester
              </label>
            </div>
          )}

          <div className="flex gap-2 mt-3">
            <button type="submit" className="fet-btn-primary flex items-center gap-1 disabled:opacity-60" disabled={busy}>
              <Save size={16} />
              {busy ? 'Saving…' : editingId ? 'Update' : 'Add'} Semester
            </button>
            <button type="button" onClick={handleCancel} className="fet-btn-secondary">
              Cancel
            </button>
          </div>
        </form>
      )}
    </div>
  );
};

export default SemesterSelector;
