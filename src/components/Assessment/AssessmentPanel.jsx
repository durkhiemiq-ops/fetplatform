import React, { useState, useEffect, useCallback } from 'react';
import {
  Loader2, Download, Trash2, Send, Plus, ChevronDown, ChevronRight,
  CheckCircle2, AlertCircle, Award, Layers,
} from 'lucide-react';
import { learningApi } from '../../lib/learning';
import { normalizeRole } from '../../lib/profile';

/**
 * Course-level assessment marks (CA / Exam) for a single classroom.
 * Lecturer: create a sheet, type marks, publish, export CSV, answer disputes.
 * Student: see own published mark and report an error.
 */
const AssessmentPanel = ({ offeringId, user }) => {
  const role = normalizeRole(user?.role);
  const isStaff = role === 'lecturer' || role === 'admin';

  const [assessments, setAssessments] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [notice, setNotice] = useState('');

  const [newOpen, setNewOpen] = useState(false);
  const [creating, setCreating] = useState(false);
  const [form, setForm] = useState({
    title: '', description: '', category: 'CA', maximum_score: '100', raw_maximum: '',
    weight: '', group: '', file: null,
  });

  const [groups, setGroups] = useState([]);
  const [groupOpen, setGroupOpen] = useState(false);
  const [creatingGroup, setCreatingGroup] = useState(false);
  const [groupForm, setGroupForm] = useState({ title: '', maximum_score: '30' });
  const [expandedGroup, setExpandedGroup] = useState(null);
  const [groupRows, setGroupRows] = useState([]);

  const [openSheet, setOpenSheet] = useState(null);
  const [sheetMarks, setSheetMarks] = useState([]);
  const [savingMarks, setSavingMarks] = useState(false);
  const [editing, setEditing] = useState({});

  const [disputing, setDisputing] = useState(null);
  const [disputeText, setDisputeText] = useState('');
  const [replies, setReplies] = useState({});

  const flash = (text) => {
    setNotice(text);
    setError('');
    window.setTimeout(() => setNotice(''), 4000);
  };
  const fail = (text) => {
    setError(text);
    setNotice('');
  };

  const load = useCallback(async () => {
    if (!offeringId) return;
    setLoading(true);
    try {
      const data = await learningApi.getAssessments(offeringId);
      setAssessments(data || []);
    } catch (err) {
      fail('Failed to load assessments.');
    } finally {
      setLoading(false);
    }
  }, [offeringId]);

  useEffect(() => { load(); }, [load]);

  const loadGroups = useCallback(async () => {
    if (!offeringId) return;
    try {
      const data = await learningApi.getGroups(offeringId);
      setGroups(data || []);
    } catch (err) {
      // Non-fatal: the group section simply stays empty.
    }
  }, [offeringId]);

  useEffect(() => { loadGroups(); }, [loadGroups]);

  const toggleGroup = async (group) => {
    if (expandedGroup === group.id) {
      setExpandedGroup(null);
      return;
    }
    setExpandedGroup(group.id);
    try {
      const full = await learningApi.getGroup(group.id);
      setGroupRows(full.students || []);
    } catch (err) {
      fail('Could not load the combined grade.');
    }
  };

  const handleCreateGroup = async () => {
    if (!groupForm.title.trim()) {
      fail('Give the grade a title.');
      return;
    }
    setCreatingGroup(true);
    try {
      await learningApi.createGroup(offeringId, {
        title: groupForm.title.trim(),
        maximum_score: groupForm.maximum_score || '30',
      });
      setGroupForm({ title: '', maximum_score: '30' });
      setGroupOpen(false);
      flash('Grade created. Assign your CAs to it below.');
      loadGroups();
    } catch (err) {
      fail(err.response?.data?.error?.message || 'Could not create the grade.');
    } finally {
      setCreatingGroup(false);
    }
  };

  const setGroupStatus = async (group, status) => {
    try {
      await learningApi.updateGroup(group.id, { status });
      flash(status === 'PUBLISHED' ? `${group.title} published.` : 'Moved back to draft.');
      loadGroups();
    } catch (err) {
      fail(err.response?.data?.error?.message || 'Could not update.');
    }
  };

  const handleDeleteGroup = async (group) => {
    if (!window.confirm(`Delete "${group.title}"? The assessments stay, they just leave this grade.`)) return;
    try {
      await learningApi.deleteGroup(group.id);
      flash('Grade deleted.');
      loadGroups();
      load();
    } catch (err) {
      fail(err.response?.data?.error?.message || 'Could not delete.');
    }
  };

  // Mirror of the backend conversion so the lecturer sees the effect live.
  const convert = (raw, assessment) => {
    if (raw === '' || raw === null || raw === undefined) return null;
    const n = Number(raw);
    if (Number.isNaN(n)) return null;
    const scale = Number(assessment.marking_scale_value || assessment.maximum_score);
    const reported = Number(assessment.maximum_score);
    if (!scale) return null;
    return Math.round((n * reported) / scale * 100) / 100;
  };

  const handleCreate = async () => {
    if (!form.title.trim()) {
      fail('Give the assessment a title.');
      return;
    }
    setCreating(true);
    try {
      let attachmentId = null;
      if (form.file) {
        const uploaded = await learningApi.uploadFile(form.file, offeringId);
        attachmentId = uploaded.id;
      }
      await learningApi.createAssessment(offeringId, {
        title: form.title.trim(),
        description: form.description,
        category: form.category,
        maximum_score: form.maximum_score || '100',
        raw_maximum: form.raw_maximum === '' ? null : form.raw_maximum,
        weight: form.weight || '0',
        ...(form.group ? { group: form.group } : {}),
        ...(attachmentId ? { attachment: attachmentId } : {}),
      });
      setForm({ title: '', description: '', category: 'CA', maximum_score: '100', raw_maximum: '', weight: '', group: '', file: null });
      setNewOpen(false);
      flash('Assessment created as a draft. Enter marks, then publish.');
      load();
    } catch (err) {
      fail(err.response?.data?.error?.message || 'Could not create the assessment.');
    } finally {
      setCreating(false);
    }
  };

  const toggleSheet = async (assessment) => {
    if (openSheet === assessment.id) {
      setOpenSheet(null);
      return;
    }
    setOpenSheet(assessment.id);
    setEditing({});
    try {
      const full = await learningApi.getAssessment(assessment.id);
      setSheetMarks(full.marks || []);
    } catch (err) {
      fail('Could not load the mark sheet.');
    }
  };

  const handleSaveMarks = async (assessment) => {
    setSavingMarks(true);
    try {
      const payload = sheetMarks.map((m) => ({
        student: m.student,
        score: editing[m.id] !== undefined ? editing[m.id] : (m.score ?? ''),
        comment: m.comment || '',
      }));
      const res = await learningApi.saveMarks(assessment.id, payload);
      if (res.errors?.length) {
        fail(`Saved ${res.saved}, but ${res.errors.length} rejected — ${res.errors[0]}`);
      } else {
        flash(`Saved ${res.saved} mark${res.saved === 1 ? '' : 's'}.`);
      }
      setEditing({});
      load();
    } catch (err) {
      fail(err.response?.data?.error?.message || 'Could not save the marks.');
    } finally {
      setSavingMarks(false);
    }
  };

  const setStatus = async (assessment, status) => {
    try {
      await learningApi.publishSheet(assessment.id, status);
      flash(status === 'PUBLISHED'
        ? `${assessment.title} published. Students can now see their marks.`
        : 'Moved back to draft. Students can no longer see it.');
      load();
    } catch (err) {
      fail(err.response?.data?.error?.message || 'Could not update.');
    }
  };

  const handleDelete = async (assessment) => {
    if (!window.confirm(`Delete "${assessment.title}" and all its marks?`)) return;
    try {
      await learningApi.deleteAssessment(assessment.id);
      flash('Assessment deleted.');
      load();
    } catch (err) {
      fail(err.response?.data?.error?.message || 'Could not delete.');
    }
  };

  const handleDispute = async (mark) => {
    if (!disputeText.trim()) {
      fail('Tell your lecturer what is wrong.');
      return;
    }
    try {
      await learningApi.raiseDispute(mark.id, disputeText.trim());
      setDisputing(null);
      setDisputeText('');
      flash('Sent to your lecturer. They will review it.');
      load();
    } catch (err) {
      fail(err.response?.data?.error?.message || 'Could not send the report.');
    }
  };

  const handleResolve = async (mark) => {
    const text = replies[mark.id];
    if (!text || !text.trim()) {
      fail('Write a response for the student.');
      return;
    }
    try {
      await learningApi.resolveDispute(mark.id, text.trim());
      setReplies((prev) => ({ ...prev, [mark.id]: '' }));
      flash('Dispute resolved.');
      const full = await learningApi.getAssessment(openSheet);
      setSheetMarks(full.marks || []);
      load();
    } catch (err) {
      fail(err.response?.data?.error?.message || 'Could not resolve.');
    }
  };

  if (!offeringId) {
    return (
      <div className="fet-card p-10 text-center text-sm text-text-secondary">
        Select a classroom to manage its assessments.
      </div>
    );
  }

  return (
    <div className="space-y-4">
      {error && (
        <div className="bg-red-50 border border-red-200 text-red-700 px-4 py-3 rounded-xl text-sm">{error}</div>
      )}
      {notice && (
        <div className="bg-green-50 border border-green-200 text-green-800 px-4 py-3 rounded-xl text-sm">{notice}</div>
      )}

      <div className="flex items-center justify-between gap-3 flex-wrap">
        <p className="text-sm text-text-secondary">
          {isStaff
            ? 'Enter marks for each CA or exam, then publish so students can check and report issues.'
            : 'Check your marks. If something looks wrong, report it to your lecturer.'}
        </p>
        {isStaff && (
          <button onClick={() => setNewOpen(!newOpen)} className="fet-btn-primary flex items-center gap-2">
            {newOpen ? <ChevronDown size={16} /> : <Plus size={16} />} New assessment
          </button>
        )}
      </div>

      {isStaff && (
        <div className="fet-card p-5">
          <div className="flex items-center justify-between gap-3 flex-wrap">
            <div>
              <h3 className="text-[15px] font-semibold text-text-primary flex items-center gap-2">
                <Layers size={16} className="text-primary" /> Combined grades
              </h3>
              <p className="text-xs text-text-secondary mt-0.5">
                Roll several CAs into one reported grade, e.g. all CAs into one CA out of 30.
              </p>
            </div>
            <button onClick={() => setGroupOpen(!groupOpen)} className="fet-btn-secondary flex items-center gap-2 text-sm">
              {groupOpen ? <ChevronDown size={15} /> : <Plus size={15} />} New combined grade
            </button>
          </div>

          {groupOpen && (
            <div className="mt-4 grid grid-cols-1 sm:grid-cols-[1fr_140px_auto] gap-3 items-end">
              <label className="flex flex-col gap-1">
                <span className="fet-label">Title</span>
                <input
                  type="text"
                  value={groupForm.title}
                  onChange={(e) => setGroupForm({ ...groupForm, title: e.target.value })}
                  className="fet-input"
                  placeholder="e.g. Continuous Assessment"
                />
              </label>
              <label className="flex flex-col gap-1">
                <span className="fet-label">Out of</span>
                <input
                  type="number" min="0"
                  value={groupForm.maximum_score}
                  onChange={(e) => setGroupForm({ ...groupForm, maximum_score: e.target.value })}
                  className="fet-input"
                />
              </label>
              <button
                onClick={handleCreateGroup}
                disabled={creatingGroup || !groupForm.title.trim()}
                className="fet-btn-primary flex items-center gap-2"
              >
                {creatingGroup ? <Loader2 className="h-4 w-4 animate-spin" /> : <Plus size={15} />} Create
              </button>
            </div>
          )}

          {groups.length > 0 && (
            <div className="mt-4 space-y-2">
              {groups.map((g) => {
                const published = g.status === 'PUBLISHED';
                const open = expandedGroup === g.id;
                return (
                  <div key={g.id} className="p-3 rounded-xl bg-page-bg border border-border-default">
                    <div className="flex items-center justify-between gap-3 flex-wrap">
                      <button onClick={() => toggleGroup(g)} className="flex items-center gap-2 min-w-0 text-left">
                        {open ? <ChevronDown size={15} className="shrink-0" /> : <ChevronRight size={15} className="shrink-0" />}
                        <span className="min-w-0">
                          <span className="block font-semibold text-text-primary text-sm">{g.title}</span>
                          <span className="block text-xs text-text-secondary">
                            Out of {g.maximum_score} · {g.member_count} assessment{g.member_count === 1 ? '' : 's'} ·{' '}
                            {g.published_members} published
                            {g.average != null ? ` · class average ${g.average}` : ''}
                          </span>
                        </span>
                      </button>
                      <div className="flex items-center gap-2 flex-wrap">
                        <span className={`text-xs font-medium px-2 py-0.5 rounded-full border ${published
                          ? 'bg-green-50 text-green-700 border-green-200'
                          : 'bg-amber-50 text-amber-700 border-amber-200'}`}>
                          {published ? 'Published' : 'Draft'}
                        </span>
                        <button
                          type="button"
                          onClick={() =>
                            learningApi.downloadGroupExport(g.id).catch(() => {})
                          }
                          className="fet-btn-secondary text-xs flex items-center gap-1"
                        >
                          <Download size={13} /> CSV
                        </button>
                        <button
                          onClick={() => setGroupStatus(g, published ? 'DRAFT' : 'PUBLISHED')}
                          className="fet-btn-secondary text-xs"
                        >
                          {published ? 'Unpublish' : 'Publish'}
                        </button>
                        <button onClick={() => handleDeleteGroup(g)} className="p-1 hover:bg-red-50 rounded">
                          <Trash2 size={14} className="text-red-500" />
                        </button>
                      </div>
                    </div>

                    {g.members.length > 0 && (
                      <p className="mt-2 text-xs text-text-secondary flex flex-wrap gap-x-3 gap-y-1">
                        {g.members.map((m) => (
                          <span key={m.id}>
                            {m.title}
                            {m.is_converted ? ` (/${m.marking_scale_value})` : ''}
                          </span>
                        ))}
                      </p>
                    )}

                    {open && (
                      <div className="mt-3 overflow-x-auto">
                        <table className="fet-table">
                          <thead>
                            <tr>
                              <th>Student</th>
                              <th>Number</th>
                              {g.members.map((m) => (
                                <th key={m.id} className="text-xs">
                                  {m.title}
                                  <span className="block font-normal text-text-secondary">
                                    {m.group_weight ? `${m.group_weight}%` : 'even split'}
                                  </span>
                                </th>
                              ))}
                              <th>Total</th>
                            </tr>
                          </thead>
                          <tbody>
                            {groupRows.length === 0 && (
                              <tr>
                                <td colSpan={3 + g.members.length} className="text-center py-4 text-text-secondary text-sm">
                                  No marks recorded yet for this grade.
                                </td>
                              </tr>
                            )}
                            {groupRows.map((row) => {
                              const byId = Object.fromEntries(row.breakdown.map((b) => [b.assessment_id, b]));
                              return (
                                <tr key={row.student}>
                                  <td className="font-medium">{row.student_name}</td>
                                  <td className="text-text-secondary text-xs">{row.student_number}</td>
                                  {g.members.map((m) => {
                                    const b = byId[m.id];
                                    return (
                                      <td key={m.id} className="text-sm">
                                        {b?.points != null ? (
                                          <span title={`${b.raw_score} / ${b.marking_scale}`}>
                                            {b.points}
                                            <span className="text-text-secondary text-xs"> / {b.contributes_out_of}</span>
                                          </span>
                                        ) : (
                                          <span className="text-text-secondary">—</span>
                                        )}
                                      </td>
                                    );
                                  })}
                                  <td className="font-bold text-primary">
                                    {row.total != null ? `${row.total} / ${row.out_of}` : '—'}
                                  </td>
                                </tr>
                              );
                            })}
                          </tbody>
                        </table>
                      </div>
                    )}
                  </div>
                );
              })}
            </div>
          )}
        </div>
      )}

      {isStaff && newOpen && (
        <div className="fet-card p-5 space-y-3">
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
            <label className="flex flex-col gap-1">
              <span className="fet-label">Title *</span>
              <input
                type="text"
                value={form.title}
                onChange={(e) => setForm({ ...form, title: e.target.value })}
                className="fet-input"
                placeholder="e.g. CA 1 - Quiz"
              />
            </label>
            <label className="flex flex-col gap-1">
              <span className="fet-label">Type</span>
              <select
                value={form.category}
                onChange={(e) => {
                  const category = e.target.value;
                  setForm({
                    ...form,
                    category,
                    // CAs are conventionally out of 30, exams out of 100.
                    maximum_score: category === 'CA' ? '30' : '100',
                  });
                }}
                className="fet-input"
              >
                <option value="CA">Continuous Assessment (CA)</option>
                <option value="EXAM">Exam</option>
              </select>
            </label>
            <label className="flex flex-col gap-1">
              <span className="fet-label">Reported out of</span>
              <input
                type="number" min="0"
                value={form.maximum_score}
                onChange={(e) => setForm({ ...form, maximum_score: e.target.value })}
                className="fet-input"
              />
              <span className="text-[11px] text-text-secondary">What students see (CA = 30, Exam = 100)</span>
            </label>
            <label className="flex flex-col gap-1">
              <span className="fet-label">You mark out of (optional)</span>
              <input
                type="number" min="0"
                value={form.raw_maximum}
                onChange={(e) => setForm({ ...form, raw_maximum: e.target.value })}
                className="fet-input"
                placeholder={form.maximum_score || 'same'}
              />
              <span className="text-[11px] text-text-secondary">
                {form.raw_maximum && form.raw_maximum !== form.maximum_score
                  ? `You type marks out of ${form.raw_maximum}; students see them converted to ${form.maximum_score}.`
                  : 'Leave blank to type marks directly on the reported scale.'}
              </span>
            </label>
            <label className="flex flex-col gap-1">
              <span className="fet-label">Weight (%, optional)</span>
              <input
                type="number" min="0"
                value={form.weight}
                onChange={(e) => setForm({ ...form, weight: e.target.value })}
                className="fet-input"
                placeholder="e.g. 10"
              />
            </label>
            {groups.length > 0 && (
              <label className="flex flex-col gap-1 sm:col-span-2">
                <span className="fet-label">Combine into a grade</span>
                <select
                  value={form.group}
                  onChange={(e) => setForm({ ...form, group: e.target.value })}
                  className="fet-input"
                >
                  <option value="">Not part of a combined grade</option>
                  {groups.map((g) => (
                    <option key={g.id} value={g.id}>
                      {g.title} (out of {g.maximum_score})
                    </option>
                  ))}
                </select>
                <span className="text-[11px] text-text-secondary">
                  Several CAs can roll up into one CA out of {groups.find((g) => g.id === form.group)?.maximum_score || 30}.
                </span>
              </label>
            )}
          </div>
          <label className="flex flex-col gap-1">
            <span className="fet-label">Notes for students (optional)</span>
            <textarea
              value={form.description}
              onChange={(e) => setForm({ ...form, description: e.target.value })}
              className="fet-input min-h-[60px]"
            />
          </label>
          <label className="flex flex-col gap-1">
            <span className="fet-label">Attach mark sheet (PDF, CSV or any file)</span>
            <input
              type="file"
              onChange={(e) => setForm({ ...form, file: e.target.files[0] })}
              className="fet-input"
            />
          </label>
          <div className="flex justify-end">
            <button
              onClick={handleCreate}
              disabled={creating || !form.title.trim()}
              className="fet-btn-primary flex items-center gap-2"
            >
              {creating ? <Loader2 className="h-4 w-4 animate-spin" /> : <Send size={16} />} Create draft
            </button>
          </div>
        </div>
      )}

      {loading && (
        <div className="flex justify-center py-10"><Loader2 className="h-7 w-7 animate-spin text-primary" /></div>
      )}

      {!loading && assessments.length === 0 && (
        <div className="fet-card p-10 text-center">
          <Award size={44} className="mx-auto opacity-40 text-text-secondary" />
          <p className="mt-3 font-semibold text-text-primary">No assessments yet</p>
          <p className="text-sm text-text-secondary mt-1">
            {isStaff ? 'Create a CA or exam to start recording marks.' : 'Your lecturer has not published any marks yet.'}
          </p>
        </div>
      )}

      {!loading && assessments.map((a) => {
        const published = a.status === 'PUBLISHED';
        const expanded = openSheet === a.id;
        return (
          <div key={a.id} className="fet-card p-5">
            <div className="flex flex-wrap items-start justify-between gap-3">
              <div className="min-w-0">
                <div className="flex flex-wrap items-center gap-2">
                  <h4 className="font-bold text-text-primary">{a.title}</h4>
                  <span className="text-xs font-medium px-2.5 py-1 rounded-full border border-border-default text-text-secondary">
                    {a.category === 'EXAM' ? 'Exam' : 'CA'}
                  </span>
                  <span className={`text-xs font-medium px-2.5 py-1 rounded-full border ${published
                    ? 'bg-green-50 text-green-700 border-green-200'
                    : 'bg-amber-50 text-amber-700 border-amber-200'}`}>
                    {published ? 'Published' : 'Draft'}
                  </span>
                  {a.open_disputes > 0 && (
                    <span className="text-xs font-medium px-2.5 py-1 rounded-full border bg-red-50 text-red-700 border-red-200">
                      {a.open_disputes} dispute{a.open_disputes === 1 ? '' : 's'}
                    </span>
                  )}
                </div>
                {a.description && <p className="text-sm text-text-secondary mt-1">{a.description}</p>}
                <p className="mt-2 text-xs text-text-secondary flex flex-wrap gap-x-4 gap-y-1">
                  <span>Out of {a.maximum_score}</span>
                  {a.is_converted && (
                    <span className="text-primary">
                      You mark out of {a.marking_scale_value} → students see /{a.maximum_score}
                    </span>
                  )}
                  {a.group_title && <span>Part of: {a.group_title}</span>}
                  {a.weight ? <span>Weight {a.weight}%</span> : null}
                  {isStaff && <span>{a.graded_count}/{a.marks_count} marked</span>}
                  {isStaff && a.average_score != null && <span>Average {a.average_score}</span>}
                  {published && a.published_at && (
                    <span>Published {new Date(a.published_at).toLocaleDateString()}</span>
                  )}
                </p>
                {a.attachment_info && (
                  <button
                    type="button"
                    onClick={() =>
                      learningApi.downloadFile(a.attachment_info.id).catch(() => {})
                    }
                    className="mt-2 inline-flex items-center gap-1.5 text-sm text-primary hover:underline"
                  >
                    <Download size={14} /> {a.attachment_info.original_name}
                  </button>
                )}
              </div>

              {isStaff && (
                <div className="flex items-center gap-2 flex-wrap">
                  <button
                    type="button"
                    onClick={() =>
                      learningApi.downloadAssessmentExport(a.id).catch(() => {})
                    }
                    className="fet-btn-secondary text-sm flex items-center gap-1.5"
                    title="Download as CSV"
                  >
                    <Download size={15} /> CSV
                  </button>
                  {published ? (
                    <button
                      onClick={() => { if (window.confirm('Move back to draft? Students will no longer see it.')) setStatus(a, 'DRAFT'); }}
                      className="fet-btn-secondary text-sm"
                    >
                      Unpublish
                    </button>
                  ) : (
                    <button onClick={() => setStatus(a, 'PUBLISHED')} className="fet-btn-primary text-sm flex items-center gap-1.5">
                      <CheckCircle2 size={15} /> Publish
                    </button>
                  )}
                  <button onClick={() => handleDelete(a)} className="p-1.5 hover:bg-red-50 rounded-lg" title="Delete assessment">
                    <Trash2 size={16} className="text-red-500" />
                  </button>
                </div>
              )}
            </div>

            {!isStaff && a.my_mark && (
              <div className="mt-4 border-t border-border-default pt-4">
                <div className="flex items-center justify-between gap-3 flex-wrap">
                  <div>
                    <p className="text-xs text-text-secondary">Your score</p>
                    <p className="text-2xl font-bold text-text-primary">
                      {a.my_mark.reported_score ?? a.my_mark.score ?? '—'}
                      <span className="text-sm font-normal text-text-secondary"> / {a.maximum_score}</span>
                    </p>
                  </div>
                  {a.my_mark.dispute_status === 'RESOLVED' && (
                    <div className="text-xs text-green-700 bg-green-50 border border-green-200 rounded-lg px-3 py-2 max-w-xs">
                      <p className="font-semibold">Lecturer replied</p>
                      <p className="mt-0.5">{a.my_mark.dispute_response}</p>
                    </div>
                  )}
                </div>
                {a.my_mark.dispute_status === 'OPEN' ? (
                  <p className="mt-3 text-sm text-amber-700 bg-amber-50 border border-amber-200 rounded-lg px-3 py-2">
                    Reported: &ldquo;{a.my_mark.dispute_reason}&rdquo; — waiting for your lecturer.
                  </p>
                ) : a.my_mark.dispute_status !== 'RESOLVED' && (
                  <button
                    onClick={() => { setDisputing(a.my_mark.id); setDisputeText(''); }}
                    className="mt-3 text-sm text-primary hover:underline flex items-center gap-1.5"
                  >
                    <AlertCircle size={15} /> This mark looks wrong — report it
                  </button>
                )}
                {disputing === a.my_mark.id && (
                  <div className="mt-3 p-4 rounded-xl bg-page-bg border border-border-default">
                    <textarea
                      value={disputeText}
                      onChange={(e) => setDisputeText(e.target.value)}
                      className="fet-input min-h-[70px]"
                      placeholder="Explain what is wrong with this mark…"
                    />
                    <div className="flex justify-end gap-2 mt-2">
                      <button onClick={() => setDisputing(null)} className="fet-btn-secondary text-sm">Cancel</button>
                      <button onClick={() => handleDispute(a.my_mark)} className="fet-btn-primary text-sm">Send report</button>
                    </div>
                  </div>
                )}
              </div>
            )}

            {isStaff && (
              <div className="mt-4 border-t border-border-default pt-3">
                <button onClick={() => toggleSheet(a)} className="flex items-center gap-1.5 text-sm font-medium text-primary">
                  {expanded ? <ChevronDown size={16} /> : <ChevronRight size={16} />}
                  {expanded ? 'Hide mark sheet' : `Enter / edit marks (${a.graded_count}/${a.marks_count})`}
                </button>
                {expanded && (
                  <div className="mt-3">
                    {sheetMarks.length === 0 ? (
                      <p className="text-sm text-text-secondary py-4 text-center">
                        No students are enrolled in this course yet.
                      </p>
                    ) : (
                      <>
                        <div className="overflow-x-auto">
                          <table className="fet-table">
                            <thead>
                              <tr>
                                <th>Student</th>
                                <th>Number</th>
                                <th style={{ width: 120 }}>
                                  Score {a.is_converted ? `(/${a.marking_scale_value})` : ''}
                                </th>
                                {a.is_converted && <th style={{ width: 100 }}>Student sees</th>}
                                <th>Comment</th>
                                <th>Dispute</th>
                              </tr>
                            </thead>
                            <tbody>
                              {sheetMarks.map((m) => {
                                const live = editing[m.id] !== undefined ? editing[m.id] : (m.score ?? '');
                                const shown = a.is_converted ? convert(live, a) : null;
                                return (
                                  <tr key={m.id}>
                                    <td className="font-medium">{m.student_name}</td>
                                    <td className="text-text-secondary text-xs">{m.student_number}</td>
                                    <td>
                                      <input
                                        type="number" min="0" step="0.01"
                                        className="fet-input"
                                        value={live}
                                        onChange={(e) => setEditing({ ...editing, [m.id]: e.target.value })}
                                      />
                                    </td>
                                    {a.is_converted && (
                                      <td className="text-sm text-primary font-semibold">
                                        {shown == null ? '—' : `${shown} / ${a.maximum_score}`}
                                      </td>
                                    )}
                                    <td className="text-xs text-text-secondary max-w-[200px] truncate">{m.comment || '—'}</td>
                                    <td>
                                      {m.dispute_status === 'OPEN' ? (
                                        <div className="space-y-1">
                                          <p className="text-xs text-red-700">{m.dispute_reason}</p>
                                          <input
                                            type="text" className="fet-input text-xs"
                                            placeholder="Reply to student…"
                                            value={replies[m.id] || ''}
                                            onChange={(e) => setReplies({ ...replies, [m.id]: e.target.value })}
                                          />
                                          <button onClick={() => handleResolve(m)} className="text-xs text-primary hover:underline">
                                            Resolve
                                          </button>
                                        </div>
                                      ) : m.dispute_status === 'RESOLVED' ? (
                                        <span className="text-xs text-green-700">Resolved</span>
                                      ) : (
                                        <span className="text-xs text-text-secondary">—</span>
                                      )}
                                    </td>
                                  </tr>
                                );
                              })}
                            </tbody>
                          </table>
                        </div>
                        <div className="flex justify-end mt-3">
                          <button onClick={() => handleSaveMarks(a)} disabled={savingMarks} className="fet-btn-primary flex items-center gap-2 text-sm">
                            {savingMarks ? <Loader2 className="h-4 w-4 animate-spin" /> : <CheckCircle2 size={15} />} Save marks
                          </button>
                        </div>
                      </>
                    )}
                  </div>
                )}
              </div>
            )}
          </div>
        );
      })}
    </div>
  );
};

export default AssessmentPanel;
