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
    title: '', category: 'CA', maximum_score: '100', weight: '',
  });

  const [groups, setGroups] = useState([]);
  const [groupOpen, setGroupOpen] = useState(false);
  const [creatingGroup, setCreatingGroup] = useState(false);
  const [groupForm, setGroupForm] = useState({ title: '' });
  const [expandedGroup, setExpandedGroup] = useState(null);
  // Membership currently ticked in an open collection editor. Seeded from the
  // collection's own `sheets` so what is saved is exactly what the server
  // reported, never a locally invented set.
  const [groupSheets, setGroupSheets] = useState([]);
  const [savingMembership, setSavingMembership] = useState(false);

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
    // Seed from the list copy first so the editor opens instantly, then confirm
    // against the detail read rather than trusting a possibly stale listing.
    setGroupSheets(group.sheets || []);
    try {
      const full = await learningApi.getGroup(group.id);
      setGroupSheets(full.sheets || []);
    } catch (err) {
      // Non-fatal: the editor keeps the membership the listing reported.
    }
  };

  const toggleSheetInGroup = (sheetId) => {
    setGroupSheets((current) => (
      current.includes(sheetId)
        ? current.filter((id) => id !== sheetId)
        : [...current, sheetId]
    ));
  };

  const saveMembership = async (group) => {
    setSavingMembership(true);
    try {
      await learningApi.updateGroup(group.id, { sheets: groupSheets });
      flash('Sheets updated. Publication state was recalculated.');
      await loadGroups();
      await load();
    } catch (err) {
      fail(err.response?.data?.error?.message || 'Could not update the sheets.');
    } finally {
      setSavingMembership(false);
    }
  };

  const handleCreateGroup = async () => {
    if (!groupForm.title.trim()) {
      fail('Give the collection a title.');
      return;
    }
    setCreatingGroup(true);
    try {
      // No maximum_score: a collection has no score of its own, only sheets.
      await learningApi.createGroup(offeringId, {
        title: groupForm.title.trim(),
      });
      setGroupForm({ title: '' });
      setGroupOpen(false);
      flash('Collection created. Add the sheets it should publish below.');
      loadGroups();
    } catch (err) {
      fail(err.response?.data?.error?.message || 'Could not create the collection.');
    } finally {
      setCreatingGroup(false);
    }
  };

  const publishGroupSheets = async (group) => {
    // Guarded in the UI *and* on the server: an empty collection answers
    // EMPTY_GROUP, and an already-complete one is a no-op rather than a claim
    // that new work happened.
    if (group.sheet_count === 0 || group.publication_state === 'PUBLISHED') return;
    try {
      const res = await learningApi.publishGroup(group.id);
      if (res.newly_published) {
        flash(`${group.title}: published ${res.newly_published} of ${res.sheet_count} sheet${res.sheet_count === 1 ? '' : 's'}.`);
      } else {
        flash(`${group.title}: every sheet was already published.`);
      }
      await loadGroups();
      await load();
    } catch (err) {
      fail(err.response?.data?.error?.message || 'Could not publish the sheets.');
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
      // Only fields the sheet endpoint accepts. `description`, `raw_maximum`
      // and `attachment` have no column on `AssessmentSheet`, so posting them
      // used to look successful and store nothing (and the attachment upload
      // left an orphan file behind).
      await learningApi.createAssessment(offeringId, {
        title: form.title.trim(),
        category: form.category,
        maximum_score: form.maximum_score || '100',
        weight: form.weight || '0',
      });
      setForm({ title: '', category: 'CA', maximum_score: '100', weight: '' });
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
      // A sheet's release changes every collection it belongs to, so the
      // derived state on those cards has to be recomputed too.
      loadGroups();
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
            <div className="mt-4 grid grid-cols-1 sm:grid-cols-[1fr_auto] gap-3 items-end">
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
                const state = g.publication_state || 'DRAFT';
                const sheetCount = g.sheet_count ?? 0;
                const publishedCount = g.published_sheet_count ?? 0;
                const open = expandedGroup === g.id;
                // Every label here describes *sheets*, never "members": this
                // is a collection of assessment sheets and nothing else.
                const publishLabel = state === 'PUBLISHED'
                  ? 'Published'
                  : publishedCount > 0
                    ? 'Publish remaining sheets'
                    : 'Publish all sheets';
                const badgeClass = state === 'PUBLISHED'
                  ? 'bg-green-50 text-green-700 border-green-200'
                  : state === 'PARTIALLY_PUBLISHED'
                    ? 'bg-blue-50 text-blue-700 border-blue-200'
                    : 'bg-amber-50 text-amber-700 border-amber-200';
                const badgeLabel = state === 'PARTIALLY_PUBLISHED'
                  ? 'Partially published'
                  : state === 'PUBLISHED' ? 'Published' : 'Draft';
                const publishDisabled = sheetCount === 0 || state === 'PUBLISHED';
                return (
                  <div key={g.id} className="p-3 rounded-xl bg-page-bg border border-border-default">
                    <div className="flex items-center justify-between gap-3 flex-wrap">
                      <button onClick={() => toggleGroup(g)} className="flex items-center gap-2 min-w-0 text-left">
                        {open ? <ChevronDown size={15} className="shrink-0" /> : <ChevronRight size={15} className="shrink-0" />}
                        <span className="min-w-0">
                          <span className="block font-semibold text-text-primary text-sm">{g.title}</span>
                          <span className="block text-xs text-text-secondary">
                            {sheetCount} sheet{sheetCount === 1 ? '' : 's'} · {publishedCount} published
                          </span>
                        </span>
                      </button>
                      <div className="flex items-center gap-2 flex-wrap">
                        <span className={`text-xs font-medium px-2 py-0.5 rounded-full border ${badgeClass}`}>
                          {badgeLabel}
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
                          type="button"
                          onClick={() => publishGroupSheets(g)}
                          disabled={publishDisabled}
                          title={sheetCount === 0 ? 'This collection has no sheets to publish.' : undefined}
                          className="fet-btn-secondary text-xs"
                        >
                          {publishLabel}
                        </button>
                        <button onClick={() => handleDeleteGroup(g)} className="p-1 hover:bg-red-50 rounded">
                          <Trash2 size={14} className="text-red-500" />
                        </button>
                      </div>
                    </div>

                    <div className="mt-2 flex flex-wrap items-center gap-2">
                      {sheetCount === 0 ? (
                        <span className="text-[11px] text-text-secondary">No sheets in this collection yet.</span>
                      ) : (g.sheets_detail || []).map((s) => (
                        <span
                          key={s.id}
                          className="text-[11px] px-2 py-0.5 rounded-full bg-white border border-border-default text-text-secondary"
                        >
                          {s.title} · {s.status === 'PUBLISHED' ? 'published' : 'draft'}
                        </span>
                      ))}
                    </div>

                    {open && (
                      <div className="mt-3 rounded-xl bg-white border border-border-default p-3 space-y-3">
                        <div className="flex items-center justify-between gap-2">
                          <span className="fet-label">Sheets in this collection</span>
                          <span className="text-[11px] text-text-secondary">{groupSheets.length} ticked</span>
                        </div>
                        {assessments.length === 0 ? (
                          <p className="text-xs text-text-secondary">
                            Create an assessment sheet first, then tick it in here.
                          </p>
                        ) : (
                          <ul className="space-y-1 max-h-56 overflow-y-auto pr-1">
                            {assessments.map((a) => (
                              <li key={a.id}>
                                <label className="flex items-start gap-2 text-sm text-text-primary cursor-pointer">
                                  <input
                                    type="checkbox"
                                    className="mt-1"
                                    checked={groupSheets.includes(a.id)}
                                    onChange={() => toggleSheetInGroup(a.id)}
                                  />
                                  <span>
                                    {a.title}
                                    <span className="text-text-secondary text-xs">
                                      {' '}· {a.status === 'PUBLISHED' ? 'published' : 'draft'}
                                    </span>
                                  </span>
                                </label>
                              </li>
                            ))}
                          </ul>
                        )}
                        <div className="flex justify-end gap-2">
                          <button type="button" onClick={() => toggleGroup(g)} className="fet-btn-secondary text-xs">
                            Close
                          </button>
                          <button
                            type="button"
                            onClick={() => saveMembership(g)}
                            disabled={savingMembership}
                            className="fet-btn-primary text-xs flex items-center gap-1"
                          >
                            {savingMembership ? <Loader2 size={13} className="animate-spin" /> : null}
                            Save sheets
                          </button>
                        </div>
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
              <span className="fet-label">Weight (%, optional)</span>
              <input
                type="number" min="0"
                value={form.weight}
                onChange={(e) => setForm({ ...form, weight: e.target.value })}
                className="fet-input"
                placeholder="e.g. 10"
              />
            </label>
            {/* Membership is edited on the collection card, not here: the
                sheet-create payload has no `group` field on the server, so a
                select here would be silently dropped. The same rule removes
                `raw_maximum`, `description` and the attachment picker — the
                sheet model has no such columns, and a control that posts a
                value nobody stores is worse than no control. */}
          </div>
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
