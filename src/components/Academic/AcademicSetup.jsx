import React, { useState, useEffect, useCallback } from 'react';
import { Building2, CalendarRange, Plus, Check, X } from 'lucide-react';
import { SectionHeader, Card, CardBody, CardHead, DataTable, Pill, Callout, EmptyState, Tabs } from '../UI';
import { academicsApi } from '../../lib/academics';
import { errorMessage } from '../../lib/enrollment';
import { formatDate } from '../../lib/format';

const SemesterPanel = () => {
  const [rows, setRows] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [notice, setNotice] = useState('');
  const [busy, setBusy] = useState('');

  const load = useCallback(async () => {
    setLoading(true);
    setError('');
    try {
      setRows((await academicsApi.semesters()) || []);
    } catch (err) {
      setError(errorMessage(err, 'Could not load semesters.'));
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { load(); }, [load]);

  const activate = async (semester) => {
    setBusy(semester.id);
    setError('');
    setNotice('');
    try {
      await academicsApi.activateSemester(semester.id);
      setNotice(`${semester.name} is now the active semester.`);
      await load();
    } catch (err) {
      setError(errorMessage(err, 'Could not activate that semester.'));
    } finally {
      setBusy('');
    }
  };

  const columns = [
    { key: 'name', label: 'Semester' },
    { key: 'academic_year', label: 'Year', width: '110px' },
    { key: 'number', label: 'No.', width: '70px' },
    { key: 'start_date', label: 'Starts', width: '130px', render: (r) => formatDate(r.start_date) },
    { key: 'end_date', label: 'Ends', width: '130px', render: (r) => formatDate(r.end_date) },
    {
      key: 'registration_deadline',
      label: 'Registration closes',
      width: '160px',
      render: (r) => (r.registration_deadline ? formatDate(r.registration_deadline) : '—'),
    },
    {
      key: 'is_active',
      label: 'State',
      width: '190px',
      render: (r) => (r.is_active
        ? <Pill tone="ok" dot>Active</Pill>
        : <button
            type="button"
            onClick={() => activate(r)}
            disabled={busy === r.id}
            className="fet-btn-secondary text-[12px]"
          >
            <Check size={13} /> {busy === r.id ? 'Activating...' : 'Make active'}
          </button>),
    },
  ];

  return (
    <div className="space-y-4">
      {error ? <Callout tone="bad">{error}</Callout> : null}
      {notice ? <Callout tone="ok">{notice}</Callout> : null}

      <Callout tone="in">
        Exactly one semester is active at a time. Course registration, enrolment and
        carry-over all read the active semester, so activating the wrong one closes
        student registration for the whole faculty.
      </Callout>

      <Card accent="hub">
        <CardHead title="Semesters" square="hub" />
        <CardBody>
          <DataTable
            columns={columns}
            rows={rows}
            empty={loading
              ? <p className="text-text-secondary text-[13px] py-6 text-center">Loading semesters...</p>
              : <EmptyState icon={CalendarRange} title="No semesters yet" subtitle="Create one to open registration." />}
          />
        </CardBody>
      </Card>
    </div>
  );
};

const DepartmentPanel = () => {
  const [rows, setRows] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [showForm, setShowForm] = useState(false);
  const [busy, setBusy] = useState(false);
  const [form, setForm] = useState({ code: '', name: '', faculty: '', description: '' });

  const load = useCallback(async () => {
    setLoading(true);
    setError('');
    try {
      setRows((await academicsApi.departments()) || []);
    } catch (err) {
      setError(errorMessage(err, 'Could not load departments.'));
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { load(); }, [load]);

  const submit = async (e) => {
    e.preventDefault();
    setBusy(true);
    setError('');
    try {
      await academicsApi.createDepartment({
        code: form.code.trim().toUpperCase(),
        name: form.name.trim(),
        faculty: form.faculty,
        description: form.description.trim(),
      });
      setForm({ code: '', name: '', faculty: '', description: '' });
      setShowForm(false);
      await load();
    } catch (err) {
      setError(errorMessage(err, 'Could not create that department.'));
    } finally {
      setBusy(false);
    }
  };

  const columns = [
    { key: 'code', label: 'Code', width: '100px', render: (r) => <b className="num">{r.code}</b> },
    { key: 'name', label: 'Department' },
    { key: 'faculty_name', label: 'Faculty', render: (r) => r.faculty_name || '—' },
    {
      key: 'status',
      label: 'State',
      width: '110px',
      render: (r) => <Pill tone={r.status === 'ACTIVE' ? 'ok' : 'mute'}>{r.status}</Pill>,
    },
  ];

  return (
    <div className="space-y-4">
      {error ? <Callout tone="bad">{error}</Callout> : null}

      <Card accent="hub">
        <CardHead title="Departments" square="hub">
          <button type="button" onClick={() => setShowForm((v) => !v)} className="fet-btn-primary text-[12px]">
            {showForm ? <X size={14} /> : <Plus size={14} />}
            {showForm ? 'Cancel' : 'New department'}
          </button>
        </CardHead>
        <CardBody>
          {showForm ? (
            <form onSubmit={submit} className="space-y-3 mb-5 p-4 rounded-lg bg-page-bg">
              <div className="grid sm:grid-cols-2 gap-3">
                <div>
                  <label className="fet-label">Code</label>
                  <input
                    className="fet-input"
                    value={form.code}
                    onChange={(e) => setForm({ ...form, code: e.target.value })}
                    placeholder="CS"
                    required
                  />
                </div>
                <div>
                  <label className="fet-label">Name</label>
                  <input
                    className="fet-input"
                    value={form.name}
                    onChange={(e) => setForm({ ...form, name: e.target.value })}
                    placeholder="Computer Science"
                    required
                  />
                </div>
              </div>
              <div>
                <label className="fet-label">Faculty</label>
                <input
                  className="fet-input"
                  value={form.faculty}
                  onChange={(e) => setForm({ ...form, faculty: e.target.value })}
                  placeholder="Faculty UUID"
                />
              </div>
              <div>
                <label className="fet-label">Description</label>
                <input
                  className="fet-input"
                  value={form.description}
                  onChange={(e) => setForm({ ...form, description: e.target.value })}
                />
              </div>
              <div className="flex justify-end">
                <button type="submit" className="fet-btn-primary" disabled={busy}>
                  {busy ? 'Creating...' : 'Create department'}
                </button>
              </div>
            </form>
          ) : null}

          <DataTable
            columns={columns}
            rows={rows}
            empty={loading
              ? <p className="text-text-secondary text-[13px] py-6 text-center">Loading departments...</p>
              : <EmptyState icon={Building2} title="No departments yet" subtitle="Students cannot register until a department exists." />}
          />
        </CardBody>
      </Card>
    </div>
  );
};

const AcademicSetup = () => {
  const [tab, setTab] = useState('semesters');

  return (
    <div className="space-y-5">
      <SectionHeader
        area="hub"
        icon={Building2}
        title="Academic setup"
        subtitle="The reference data the whole platform depends on: which semester is live, and which departments exist."
      />
      <Tabs
        active={tab}
        onChange={setTab}
        tabs={[
          { key: 'semesters', label: 'Semesters', icon: CalendarRange },
          { key: 'departments', label: 'Departments', icon: Building2 },
        ]}
      />
      {tab === 'semesters' ? <SemesterPanel /> : <DepartmentPanel />}
    </div>
  );
};

export default AcademicSetup;
