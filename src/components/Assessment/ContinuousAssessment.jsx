import React, { useState, useEffect, useCallback, useMemo } from 'react';
import {
  Save, FileText, Users, Target, Code, Award,
  Presentation, Search, CheckCircle, Star, AlertCircle
} from 'lucide-react';
import { useAppContext } from '../../context/AppContext';
import { getAssessments, createAssessment, updateAssessment } from '../../api/assessments';

const MAX_PER_CATEGORY = 20;

/**
 * ContinuousAssessment — wired to /api/v1/assessments/.
 *
 * L1/H5: previously this read groups and saved results in localStorage, so a
 * lecturer's assessment existed only in their browser and a student could never
 * see a released result. BR-130..132: the backend owns the record, audits every
 * change, and strips `private_notes` from a student's own view.
 *
 * Model note: `Assessment` has ONE `score` column, not a five-category
 * breakdown. The category total is persisted as `score`; the per-category
 * breakdown and feedback are carried in `private_notes` as a labelled block so
 * nothing is lost. The UI keeps the richer five-category entry.
 */
const ContinuousAssessment = ({ user }) => {
  const { students, memberships } = useAppContext();
  const [selectedStudent, setSelectedStudent] = useState(null);
  const [searchTerm, setSearchTerm] = useState('');
  const [records, setRecords] = useState([]); // API rows
  const [scores, setScores] = useState({});
  const [feedback, setFeedback] = useState('');
  const [success, setSuccess] = useState('');
  const [error, setError] = useState('');
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);

  const userRole = user?.role || 'student';
  const isLecturer = userRole === 'lecturer' || userRole === 'admin';
  const lecturerName = user?.fullName || 'Lecturer';

  // Group names come from project membership, not localStorage.
  const groupNames = useMemo(() => {
    const names = new Map();
    memberships.forEach((m) => {
      if (m.groupId && !names.has(m.studentId)) names.set(m.studentId, m.groupId);
    });
    return names;
  }, [memberships]);

  const load = useCallback(async () => {
    setLoading(true);
    setError('');
    try {
      const rows = await getAssessments();
      setRecords(Array.isArray(rows) ? rows : []);
    } catch (err) {
      setError(err.message || 'Could not load assessments.');
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  // Index API rows by student id for quick lookup.
  const byStudent = useMemo(() => {
    const map = {};
    records.forEach((r) => {
      if (r.student) map[r.student] = r;
    });
    return map;
  }, [records]);

  const emptyScores = () => ({
    proposal: 0, research: 0, implementation: 0, contribution: 0, presentation: 0,
  });

  /** Recover the five-category breakdown stored in private_notes. */
  const parseBreakdown = (record) => {
    const base = emptyScores();
    if (!record || !record.private_notes) return base;
    const marker = '[breakdown]';
    const idx = record.private_notes.indexOf(marker);
    if (idx === -1) return base;
    try {
      const parsed = JSON.parse(record.private_notes.slice(idx + marker.length).split('\n')[0]);
      return { ...base, ...parsed };
    } catch {
      return base;
    }
  };

  /** Compose private_notes: human feedback + a machine-readable breakdown. */
  const composeNotes = () => {
    const json = JSON.stringify(scores);
    return `${feedback}\n${'[breakdown]'}${json}`;
  };

  const assessmentStudents = students.map((s) => ({
    id: s.id,
    name: `${s.first_name || ''} ${s.last_name || ''}`.trim() || s.username,
    username: s.username,
    group: groupNames.get(s.id) || 'Unassigned',
  }));

  const filteredStudents = assessmentStudents.filter((s) =>
    s.name.toLowerCase().includes(searchTerm.toLowerCase()) ||
    (s.username || '').toLowerCase().includes(searchTerm.toLowerCase())
  );

  const handleSelectStudent = (student) => {
    setSelectedStudent(student);
    setSuccess('');
    setError('');
    setScores(parseBreakdown(byStudent[student.id]));
  };

  const handleScoreChange = (category, value) => {
    const num = Math.min(MAX_PER_CATEGORY, Math.max(0, parseInt(value, 10) || 0));
    setScores((prev) => ({ ...prev, [category]: num }));
  };

  const total = useMemo(
    () => Object.values(scores).reduce((sum, v) => sum + (Number(v) || 0), 0),
    [scores]
  );

  const handleSave = async () => {
    if (!selectedStudent) return;
    setSaving(true);
    setError('');
    try {
      const existing = byStudent[selectedStudent.id];
      const payload = {
        score: total,
        private_notes: composeNotes(),
        released: true,
      };
      if (existing) {
        await updateAssessment(existing.id, payload);
      } else {
        await createAssessment({ student: selectedStudent.id, ...payload });
      }
      setSuccess(`Assessment saved and released to ${selectedStudent.name}`);
      setTimeout(() => setSuccess(''), 4000);
      await load();
    } catch (err) {
      setError(err.message || 'Could not save the assessment.');
    } finally {
      setSaving(false);
    }
  };

  const assessmentCategories = [
    { key: 'proposal', label: 'Proposal', icon: FileText, max: MAX_PER_CATEGORY },
    { key: 'research', label: 'Research', icon: Target, max: MAX_PER_CATEGORY },
    { key: 'implementation', label: 'Implementation', icon: Code, max: MAX_PER_CATEGORY },
    { key: 'contribution', label: 'Contribution', icon: Users, max: MAX_PER_CATEGORY },
    { key: 'presentation', label: 'Presentation', icon: Presentation, max: MAX_PER_CATEGORY },
  ];

  if (loading) {
    return <p className="py-8 text-center text-sm text-text-secondary">Loading assessments…</p>;
  }

  // ===== STUDENT VIEW: released results only (BR-131) =====
  if (!isLecturer) {
    // The backend already scopes this to the caller and strips private notes.
    const mine = records.filter((r) => r.student === user?.id && r.released);

    return (
      <div className="space-y-6">
        <div className="fet-welcome-banner">
          <div className="flex items-center justify-between flex-wrap gap-4">
            <div>
              <h2 className="text-2xl font-bold">Assessment Results</h2>
              <p className="text-[#8683BA] mt-1">View your released continuous assessment results</p>
              <p className="text-[#8683BA] text-sm mt-1">
                {user?.fullName || 'Student'}{user?.matricule ? ` • ${user.matricule}` : ''}
              </p>
            </div>
            <div className="bg-white/10 rounded-xl px-4 py-2 text-center">
              <p className="text-xs text-[#8683BA]">Total Score</p>
              <p className="text-xl font-bold">{mine[0]?.score != null ? `${mine[0].score}/100` : '—'}</p>
            </div>
          </div>
        </div>

        {error && (
          <div className="flex items-center gap-2 rounded-lg border border-red-200 bg-red-50 px-4 py-2.5 text-[13px] text-red-700">
            <AlertCircle size={14} /> {error}
          </div>
        )}

        {mine.length > 0 ? (
          mine.map((rec) => (
            <div key={rec.id} className="fet-card p-6">
              <div className="flex items-center justify-between mb-6 pb-4 border-b border-border-default">
                <div>
                  <h3 className="text-xl font-bold text-text-primary" style={{ fontSize: '18px' }}>
                    Result Breakdown
                  </h3>
                  <p className="text-sm text-text-secondary">
                    {rec.created_at ? `Updated ${new Date(rec.created_at).toLocaleDateString()}` : ''}
                  </p>
                </div>
                <div className="text-right">
                  <p className="text-sm text-text-secondary">Overall</p>
                  <p className="text-3xl font-bold text-text-primary">
                    {rec.score}<span className="text-lg text-text-secondary">/100</span>
                  </p>
                </div>
              </div>

              <div className="space-y-4">
                {assessmentCategories.map((cat) => {
                  const Icon = cat.icon;
                  const breakdown = parseBreakdown(rec);
                  const score = breakdown[cat.key] || 0;
                  const pct = Math.round((score / cat.max) * 100);
                  return (
                    <div key={cat.key} className="flex items-center gap-4 p-4 bg-page-bg rounded-xl">
                      <div className="p-2 bg-primary/10 rounded-lg"><Icon size={20} className="text-primary" /></div>
                      <div className="flex-1">
                        <p className="text-sm font-medium text-text-primary">{cat.label}</p>
                        <div className="w-full h-2 bg-[#D9DADB] rounded-full mt-1">
                          <div className="h-full bg-gradient-to-r from-primary to-[#8B5CF6] rounded-full" style={{ width: `${pct}%` }} />
                        </div>
                      </div>
                      <p className="text-sm font-bold text-text-primary">
                        {score}<span className="text-xs text-text-secondary">/{cat.max}</span>
                      </p>
                    </div>
                  );
                })}
              </div>
            </div>
          ))
        ) : (
          <div className="fet-card p-6 text-center">
            <FileText size={48} className="mx-auto text-text-secondary opacity-50" />
            <p className="text-text-secondary mt-4">No results have been released yet.</p>
            <p className="text-sm text-text-secondary">
              Your lecturer will publish your continuous assessment results here once available.
            </p>
          </div>
        )}
      </div>
    );
  }

  // ===== LECTURER VIEW =====
  return (
    <div className="space-y-6">
      <div className="fet-welcome-banner">
        <div className="flex items-center justify-between flex-wrap gap-4">
          <div>
            <h2 className="text-2xl font-bold">Continuous Assessment</h2>
            <p className="text-[#8683BA] mt-1">Assess students across the entire project journey</p>
            <p className="text-[#8683BA] text-sm mt-1">👨‍🏫 {lecturerName}</p>
          </div>
          <div className="bg-white/10 rounded-xl px-4 py-2 text-center">
            <p className="text-xs text-[#8683BA]">Students</p>
            <p className="text-xl font-bold">{assessmentStudents.length}</p>
          </div>
        </div>
      </div>

      {success && (
        <div className="flex items-center gap-2 rounded-lg border border-green-200 bg-green-50 px-4 py-3 text-sm text-green-700">
          <CheckCircle size={18} /> {success}
        </div>
      )}
      {error && (
        <div className="flex items-center gap-2 rounded-lg border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-700">
          <AlertCircle size={16} /> {error}
        </div>
      )}

      <div className="fet-card p-6">
        <div className="relative">
          <Search className="absolute left-3 top-1/2 transform -translate-y-1/2 text-text-secondary" size={18} />
          <input
            type="text"
            placeholder="Search students by name or username..."
            value={searchTerm}
            onChange={(e) => setSearchTerm(e.target.value)}
            className="w-full pl-10 pr-4 py-2 fet-input"
          />
        </div>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        <div className="lg:col-span-1">
          <div className="fet-card p-4">
            <h3 className="text-sm font-semibold text-text-secondary uppercase tracking-wider mb-3">Students</h3>
            <div className="space-y-2 max-h-[400px] overflow-y-auto">
              {filteredStudents.map((student) => {
                const rec = byStudent[student.id];
                return (
                  <button
                    key={student.id}
                    onClick={() => handleSelectStudent(student)}
                    className={`w-full text-left p-3 rounded-xl transition-colors ${
                      selectedStudent?.id === student.id
                        ? 'bg-primary/10 border-2 border-primary'
                        : 'bg-page-bg hover:bg-[#E7E8E9]'
                    }`}
                  >
                    <div className="flex items-start justify-between gap-2">
                      <div>
                        <p className="font-medium text-text-primary">{student.name}</p>
                        <p className="text-xs text-text-secondary">@{student.username}</p>
                      </div>
                      <span className={`fet-badge ${rec ? 'fet-badge-active' : 'fet-badge-inactive'}`}>
                        {rec ? (rec.released ? 'Released' : 'Draft') : 'Not Assessed'}
                      </span>
                    </div>
                    {rec && (
                      <div className="mt-1">
                        <div className="w-full h-1.5 bg-page-bg rounded-full overflow-hidden">
                          <div
                            className="h-full bg-gradient-to-r from-primary to-[#8B5CF6] rounded-full"
                            style={{ width: `${rec.score || 0}%` }}
                          />
                        </div>
                        <p className="text-xs text-text-secondary mt-0.5">Score: {rec.score || 0}/100</p>
                      </div>
                    )}
                  </button>
                );
              })}
              {filteredStudents.length === 0 && (
                <p className="text-center text-text-secondary py-4 text-[13px]">No students found</p>
              )}
            </div>
          </div>
        </div>

        <div className="lg:col-span-2">
          <div className="fet-card p-6">
            {selectedStudent ? (
              <>
                <div className="flex items-center justify-between mb-6 pb-4 border-b border-border-default">
                  <div>
                    <h3 className="text-xl font-bold text-text-primary" style={{ fontSize: '18px' }}>
                      {selectedStudent.name}
                    </h3>
                    <p className="text-sm text-text-secondary">@{selectedStudent.username}</p>
                  </div>
                  <div className="text-right">
                    <p className="text-sm text-text-secondary">Total Score</p>
                    <p className="text-3xl font-bold text-text-primary">
                      {total}<span className="text-lg text-text-secondary">/100</span>
                    </p>
                  </div>
                </div>

                <div className="space-y-4">
                  {assessmentCategories.map((cat) => {
                    const Icon = cat.icon;
                    return (
                      <div key={cat.key} className="flex items-center gap-4 p-4 bg-page-bg rounded-xl">
                        <div className="p-2 bg-primary/10 rounded-lg"><Icon size={20} className="text-primary" /></div>
                        <div className="flex-1">
                          <label className="block text-sm font-medium text-text-primary">
                            {cat.label} (0-{cat.max})
                          </label>
                          <input
                            type="number"
                            min="0"
                            max={cat.max}
                            value={scores[cat.key] ?? 0}
                            onChange={(e) => handleScoreChange(cat.key, e.target.value)}
                            className="mt-1 w-24 px-3 py-1 fet-input"
                          />
                        </div>
                        <div className="text-right">
                          <p className="text-sm font-semibold text-text-primary">{scores[cat.key] ?? 0}</p>
                          <p className="text-xs text-text-secondary">/ {cat.max}</p>
                        </div>
                      </div>
                    );
                  })}
                </div>

                <div className="mt-6">
                  <label className="fet-label mb-2">Feedback (lecturer-only)</label>
                  <textarea
                    value={feedback}
                    onChange={(e) => setFeedback(e.target.value)}
                    placeholder="Enter feedback for the student..."
                    className="w-full px-4 py-3 fet-input resize-none"
                    rows={3}
                  />
                </div>

                <div className="mt-6 pt-4 border-t border-border-default flex justify-end">
                  <button onClick={handleSave} disabled={saving} className="fet-btn-primary flex items-center gap-2 disabled:opacity-60">
                    <Save size={18} />
                    {saving ? 'Saving…' : 'Save & Release Result'}
                  </button>
                </div>
              </>
            ) : (
              <div className="text-center py-12">
                <FileText size={48} className="mx-auto text-text-secondary opacity-50" />
                <p className="text-text-secondary mt-4">Select a student to assess</p>
                <p className="text-sm text-text-secondary">Click on a student from the list to start</p>
              </div>
            )}
          </div>
        </div>
      </div>
    </div>
  );
};

export default ContinuousAssessment;
