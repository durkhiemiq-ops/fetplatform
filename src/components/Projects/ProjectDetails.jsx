import React, { useState, useEffect, useCallback } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import {
  ArrowLeft, Plus, X, Users, CheckSquare, Target, FileText, Activity as ActivityIcon,
  ClipboardCheck, Crown, Trash2, Download, AlertCircle, UserPlus,
} from 'lucide-react';
import { projectsApi } from '../../lib/projects';
import { normalizeRole } from '../../lib/profile';
import { statusBadge, formatDateTime } from './projectUi';

const TABS = ['Overview', 'Members', 'Tasks', 'Milestones', 'Documents', 'Activity', 'Assessments'];

const initials = (name = '') =>
  name.split(' ').map((n) => n[0]).join('').toUpperCase().slice(0, 2);

const taskStatusBadge = (status) => {
  const cls = {
    TODO: 'fet-badge fet-badge-inactive',
    IN_PROGRESS: 'fet-badge fet-badge-pending',
    COMPLETED: 'fet-badge fet-badge-completed',
  }[status] || 'fet-badge fet-badge-inactive';
  return <span className={cls}>{status?.replace('_', ' ') || 'TODO'}</span>;
};

const ProjectDetails = () => {
  const { id } = useParams();
  const navigate = useNavigate();
  const role = normalizeRole(localStorage.getItem('fet_user_role'));
  const canManage = role !== 'student';
  let currentUserId = '';
  try { currentUserId = JSON.parse(localStorage.getItem('fet_user') || '{}').id || ''; } catch { /* ignore */ }

  const [project, setProject] = useState(null);
  const [groups, setGroups] = useState([]);
  const [tasks, setTasks] = useState([]);
  const [milestones, setMilestones] = useState([]);
  const [documents, setDocuments] = useState([]);
  const [contributions, setContributions] = useState([]);
  const [assessments, setAssessments] = useState([]);
  const [activeTab, setActiveTab] = useState('overview');
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [report, setReport] = useState(null);
  const [notice, setNotice] = useState('');

  const load = useCallback(async () => {
    setLoading(true);
    setError('');
    try {
      const [p, g, t, ms, d, c, a] = await Promise.all([
        projectsApi.getProject(id),
        projectsApi.listGroups(id),
        projectsApi.listTasks(id),
        projectsApi.listMilestones(id),
        projectsApi.listDocuments(id),
        projectsApi.listContributions(id),
        projectsApi.listAssessments(id),
      ]);
      setProject(p);
      setGroups(g);
      setTasks(t);
      setMilestones(ms);
      setDocuments(d);
      setContributions(c);
      setAssessments(a);
    } catch (err) {
      setError(err.response?.data?.error?.message || 'Could not load project.');
    } finally {
      setLoading(false);
    }
  }, [id]);

  useEffect(() => { load(); }, [load]);

  const flash = (msg) => {
    setNotice(msg);
    setTimeout(() => setNotice(''), 3500);
  };

  const progress =
    project && project.task_count > 0
      ? Math.round((project.completed_task_count / project.task_count) * 100)
      : 0;

  if (loading) {
    return <div className="text-center py-16 text-text-secondary text-[13px]">Loading project...</div>;
  }
  if (!project) {
    return (
      <div className="text-center py-12">
        <AlertCircle size={40} className="mx-auto text-danger mb-3" />
        <h2 className="text-[20px] font-bold text-text-primary">Project not found</h2>
        <button onClick={() => navigate('/projects')} className="mt-4 text-primary hover:underline">
          Back to Projects
        </button>
      </div>
    );
  }

  const allMembers = groups.flatMap((g) => g.members || []);

  // A group leader runs their own group's work, so they get the task controls
  // the lecturer has -- scoped to the groups they lead. `groups` already comes
  // back holding only their own group for a student, so the members offered in
  // the form are their own without any extra filtering.
  const ledGroupIds = groups
    .filter((g) => (g.members || []).some((m) => m.student === currentUserId && m.role === 'GROUP_LEADER'))
    .map((g) => g.id);
  const canManageTasks = canManage || ledGroupIds.length > 0;

  return (
    <div className="space-y-6">
      <button
        onClick={() => navigate('/projects')}
        className="flex items-center gap-2 text-text-secondary hover:text-text-primary transition-colors"
      >
        <ArrowLeft size={18} />
        <span>Back to Projects</span>
      </button>

      {notice && (
        <div className="bg-green-50 border border-green-200 text-green-700 px-4 py-3 rounded-xl text-[13px]">{notice}</div>
      )}
      {error && (
        <div className="flex items-center gap-2 bg-red-50 border border-red-200 text-red-700 px-4 py-3 rounded-xl text-[13px]">
          <AlertCircle size={16} />
          {error}
        </div>
      )}

      <div className="fet-card p-6">
        <div className="flex items-start justify-between mb-4 flex-wrap gap-3">
          <div>
            <div className="flex items-center gap-2 flex-wrap mb-1">
              {statusBadge(project.status)}
              <span className="fet-badge fet-badge-inactive">{project.course_code}</span>
            </div>
            <h2 className="text-[22px] font-bold text-text-primary">{project.title}</h2>
            <p className="text-[13px] text-text-secondary mt-1">
              Supervisor: {project.supervisor_name || '—'} • Deadline: {formatDateTime(project.deadline)}
            </p>
          </div>
          <div className="text-right">
            <p className="text-[13px] text-text-secondary">Completion</p>
            <p className="text-[22px] font-bold text-text-primary">{progress}%</p>
          </div>
        </div>

        <div className="fet-progress-bar mb-6">
          <div className="fet-progress-bar-fill" style={{ width: `${progress}%` }}></div>
        </div>

        <div className="flex gap-4 border-b border-border-default mb-6 overflow-x-auto">
          {TABS.map((tab) => (
            <button
              key={tab}
              onClick={() => setActiveTab(tab.toLowerCase())}
              className={`px-4 py-2 text-[14px] font-medium transition-colors border-b-2 whitespace-nowrap ${
                activeTab === tab.toLowerCase()
                  ? 'text-primary border-primary'
                  : 'text-text-secondary border-transparent hover:text-text-primary'
              }`}
            >
              {tab}
            </button>
          ))}
        </div>

        {activeTab === 'overview' && (
          <OverviewTab project={project} groups={groups} tasks={tasks} milestones={milestones} />
        )}
        {activeTab === 'members' && (
          <MembersTab
            projectId={id} groups={groups} members={allMembers} canManage={canManage}
            onChanged={async () => { await load(); flash('Members updated.'); }}
          />
        )}
        {activeTab === 'tasks' && (
          <TasksTab
            projectId={id} tasks={tasks} groups={groups} members={allMembers}
            canManage={canManageTasks} currentUserId={currentUserId}
            ledGroupIds={ledGroupIds}
            onChanged={async () => { await load(); }}
          />
        )}
        {activeTab === 'milestones' && (
          <MilestonesTab
            projectId={id} milestones={milestones} canManage={canManage}
            onChanged={async () => { await load(); flash('Milestones updated.'); }}
          />
        )}
        {activeTab === 'documents' && <DocumentsTab documents={documents} />}
        {activeTab === 'activity' && (
          <ActivityTab
            projectId={id} contributions={contributions}
            onChanged={async () => { await load(); flash('Contribution logged.'); }}
          />
        )}
        {activeTab === 'assessments' && (
          <AssessmentsTab
            projectId={id} assessments={assessments} members={allMembers}
            canManage={canManage}
            onChanged={async () => { await load(); }}
          />
        )}
      </div>

      {canManage && groups.length > 0 && (
        <div className="flex justify-end">
          <button
            onClick={async () => {
              try {
                const r = await projectsApi.groupReport(id, groups[0]?.id);
                setReport(r);
              } catch (err) {
                setError(err.response?.data?.error?.message || 'Could not load report.');
              }
            }}
            className="fet-btn-secondary flex items-center gap-2"
          >
            <Download size={16} />
            Group Report
          </button>
        </div>
      )}

      {report && (
        <ReportModal report={report} onClose={() => setReport(null)} />
      )}
    </div>
  );
};

const OverviewTab = ({ project, groups, tasks, milestones }) => (
  <div className="space-y-6">
    <div>
      <h4 className="font-semibold text-text-primary mb-2">Project Description</h4>
      <p className="text-[13px] text-text-secondary leading-relaxed">{project.description || 'No description provided.'}</p>
    </div>
    {project.objectives && (
      <div>
        <h4 className="font-semibold text-text-primary mb-2">Key Objectives</h4>
        <ul className="list-disc list-inside text-[13px] text-text-secondary space-y-1">
          {project.objectives.split('\n').filter((l) => l.trim()).map((line, i) => (
            <li key={i}>{line}</li>
          ))}
        </ul>
      </div>
    )}
    <div className="grid grid-cols-1 md:grid-cols-4 gap-4">
      <StatCard icon={Users} label="Groups" value={groups.length} />
      <StatCard icon={CheckSquare} label="Tasks" value={tasks.length} />
      <StatCard icon={Target} label="Milestones" value={milestones.length} />
      <StatCard
        icon={ActivityIcon} label="Contributions"
        value={project.member_count || 0}
      />
    </div>
  </div>
);

const StatCard = ({ icon: Icon, label, value }) => (
  <div className="p-4 bg-page-bg rounded-lg text-center">
    <Icon size={20} className="mx-auto text-primary mb-2" />
    <p className="text-[13px] text-text-secondary">{label}</p>
    <p className="text-xl font-bold text-text-primary">{value}</p>
  </div>
);

const MembersTab = ({ projectId, groups, members, canManage, onChanged }) => {
  const [showAddGroup, setShowAddGroup] = useState(false);
  const [showAddMember, setShowAddMember] = useState(false);
  const [candidates, setCandidates] = useState([]);
  const [busy, setBusy] = useState(false);

  const openMemberPicker = async () => {
    try {
      setCandidates(await projectsApi.candidates(projectId));
      setShowAddMember(true);
    } catch { /* no candidates */ }
  };

  const addMember = async (groupId, studentId, role) => {
    setBusy(true);
    try {
      await projectsApi.addMember(projectId, groupId, { student_id: studentId, role });
      setShowAddMember(false);
      await onChanged();
    } catch (err) {
      alert(err.response?.data?.error?.message || 'Could not add member.');
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="space-y-4">
      <div className="flex justify-between items-center">
        <h4 className="font-semibold text-text-primary">Project Groups & Members</h4>
        {canManage && (
          <div className="flex gap-2">
            <button onClick={() => setShowAddGroup(true)} className="fet-btn-secondary text-[13px] flex items-center gap-1">
              <Plus size={14} /> Add Group
            </button>
            <button onClick={openMemberPicker} className="fet-btn-primary text-[13px] flex items-center gap-1">
              <UserPlus size={14} /> Add Member
            </button>
          </div>
        )}
      </div>

      {groups.length === 0 && (
        <p className="text-center text-text-secondary py-6">No groups yet.</p>
      )}

      <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
        {groups.map((group) => (
          <div key={group.id} className="p-4 bg-page-bg rounded-lg border border-border-default">
            <div className="flex items-center justify-between mb-3">
              <h5 className="font-semibold text-text-primary">{group.name}</h5>
              <span className="fet-badge fet-badge-inactive">{group.member_count} members</span>
            </div>
            {group.description && <p className="text-[12px] text-text-secondary mb-3">{group.description}</p>}
            {(group.members || []).length === 0 && (
              <p className="text-[12px] text-text-secondary">No members assigned.</p>
            )}
            <ul className="space-y-2">
              {(group.members || []).map((m) => (
                <li key={m.id} className="flex items-center justify-between bg-white rounded-lg px-3 py-2">
                  <div className="flex items-center gap-2 min-w-0">
                    <div className="w-7 h-7 rounded-full bg-primary/10 flex items-center justify-center text-[10px] font-bold text-primary flex-shrink-0">
                      {initials(m.student_name)}
                    </div>
                    <div className="min-w-0">
                      <p className="text-[13px] font-medium text-text-primary truncate">{m.student_name}</p>
                      <p className="text-[11px] text-text-secondary">{m.role === 'GROUP_LEADER' ? 'Group Leader' : 'Member'}</p>
                    </div>
                    {m.role === 'GROUP_LEADER' && <Crown size={14} className="text-amber-500 flex-shrink-0" />}
                  </div>
                  {canManage && (
                    <button
                      onClick={async () => {
                        try {
                          await projectsApi.removeMember(projectId, group.id, m.student);
                          await onChanged();
                        } catch (err) {
                          alert(err.response?.data?.error?.message || 'Could not remove member.');
                        }
                      }}
                      className="text-red-500 hover:text-red-700 p-1"
                      title="Remove member"
                    >
                      <Trash2 size={15} />
                    </button>
                  )}
                </li>
              ))}
            </ul>
            {canManage && (
              <button
                onClick={async () => {
                  // Promote the first non-leader to group leader (BR-073).
                  const leader = group.members.find((m) => m.role === 'GROUP_LEADER');
                  const target = leader ? null : group.members[0];
                  if (!target) return;
                  try {
                    await projectsApi.removeMember(projectId, group.id, target.student);
                    await projectsApi.addMember(projectId, group.id, { student_id: target.student, role: 'GROUP_LEADER' });
                    await onChanged();
                  } catch (err) {
                    alert(err.response?.data?.error?.message || 'Could not set group leader.');
                  }
                }}
                className="text-[12px] text-primary hover:underline mt-3"
              >
                Set Group Leader
              </button>
            )}
          </div>
        ))}
      </div>

      {showAddGroup && (
        <GroupForm
          projectId={projectId}
          onClose={() => setShowAddGroup(false)}
          onDone={async () => { setShowAddGroup(false); await onChanged(); }}
        />
      )}

      {showAddMember && (
        <div className="fixed inset-0 bg-black/50 flex items-center justify-center z-50 p-4">
          <div className="bg-white rounded-xl shadow-xl max-w-lg w-full max-h-[85vh] overflow-y-auto">
            <div className="flex items-center justify-between p-5 border-b border-border-default">
              <h3 className="text-[15px] font-bold text-text-primary">Add Member</h3>
              <button onClick={() => setShowAddMember(false)} className="p-1 hover:bg-page-bg rounded-lg">
                <X size={20} className="text-text-secondary" />
              </button>
            </div>
            <div className="p-5 space-y-3">
              <h4 className="text-[13px] font-semibold text-text-secondary">Enrolled students (not yet in project)</h4>
              {candidates.length === 0 && <p className="text-[13px] text-text-secondary">No eligible students remaining.</p>}
              {candidates.map((c) => (
                <div key={c.id} className="border border-border-default rounded-xl p-3 flex items-center justify-between gap-2">
                  <div className="min-w-0">
                    <p className="text-[13px] font-medium text-text-primary">{c.full_name}</p>
                    <p className="text-[11px] text-text-secondary truncate">{c.student_number || ''} • {c.email}</p>
                  </div>
                  <div className="flex items-center gap-1.5 flex-shrink-0">
                    {groups.map((g) => (
                      <button
                        key={g.id}
                        disabled={busy}
                        onClick={() => addMember(g.id, c.id, 'MEMBER')}
                        className="fet-btn-secondary text-[11px] px-2 py-1 disabled:opacity-50"
                      >
                        {g.name}
                      </button>
                    ))}
                  </div>
                </div>
              ))}
            </div>
          </div>
        </div>
      )}
    </div>
  );
};

const GroupForm = ({ projectId, onClose, onDone }) => {
  const [name, setName] = useState('');
  const [description, setDescription] = useState('');
  const [busy, setBusy] = useState(false);

  const submit = async (e) => {
    e.preventDefault();
    setBusy(true);
    try {
      await projectsApi.createGroup(projectId, { name, description });
      await onDone();
    } catch (err) {
      alert(err.response?.data?.error?.message || 'Could not create group.');
      setBusy(false);
    }
  };

  return (
    <div className="fixed inset-0 bg-black/50 flex items-center justify-center z-50 p-4">
      <div className="bg-white rounded-xl shadow-xl max-w-md w-full">
        <div className="flex items-center justify-between p-5 border-b border-border-default">
          <h3 className="text-[15px] font-bold text-text-primary">Add Group</h3>
          <button onClick={onClose} className="p-1 hover:bg-page-bg rounded-lg"><X size={20} className="text-text-secondary" /></button>
        </div>
        <form onSubmit={submit} className="p-5 space-y-4">
          <div>
            <label className="fet-label">Group Name</label>
            <input type="text" value={name} onChange={(e) => setName(e.target.value)} required className="fet-input" />
          </div>
          <div>
            <label className="fet-label">Description</label>
            <textarea value={description} onChange={(e) => setDescription(e.target.value)} rows={2} className="fet-input resize-none" />
          </div>
          <div className="flex justify-end gap-3">
            <button type="button" onClick={onClose} className="fet-btn-secondary">Cancel</button>
            <button type="submit" className="fet-btn-primary" disabled={busy}>Create Group</button>
          </div>
        </form>
      </div>
    </div>
  );
};

const TasksTab = ({ projectId, tasks, groups, members, canManage, currentUserId, ledGroupIds = [], onChanged }) => {
  const [showForm, setShowForm] = useState(false);
  // A group leader has exactly one group they are allowed to file into, so the
  // picker is not a choice for them -- it is just noise.
  const fixedGroupId = canManage ? '' : ledGroupIds[0] || '';

  return (
    <div className="space-y-4">
      <div className="flex justify-between items-center">
        <h4 className="font-semibold text-text-primary">Project Tasks</h4>
        {canManage && (
          <button onClick={() => setShowForm(true)} className="fet-btn-primary text-[13px] flex items-center gap-1">
            <Plus size={14} /> New Task
          </button>
        )}
      </div>
      {tasks.length === 0 && <p className="text-center text-text-secondary py-6">No tasks for this project.</p>}
      <div className="space-y-2">
        {tasks.map((task) => {
          const mine = task.assigned_student && task.assigned_student === currentUserId;
          return (
            <div key={task.id} className="flex items-center justify-between gap-3 p-3 bg-page-bg rounded-lg">
              <div className="min-w-0">
                <p className="font-medium text-text-primary text-[13px]">{task.title}</p>
                <p className="text-[12px] text-text-secondary">
                  Assignee: {task.assignee_name || 'Unassigned'} • Due: {formatDateTime(task.due_at)}
                  {task.priority && <> • <span className="capitalize">{task.priority.toLowerCase()}</span></>}
                </p>
              </div>
              <div className="flex items-center gap-2 flex-shrink-0">
                {task.status === 'COMPLETED' ? (
                  taskStatusBadge(task.status)
                ) : (
                  canManage ? (
                    <>
                      {taskStatusBadge(task.status)}
                      <button
                        onClick={async () => {
                          try {
                            await projectsApi.completeTask(task.id);
                            await onChanged();
                          } catch (err) {
                            alert(err.response?.data?.error?.message || 'Could not update task.');
                          }
                        }}
                        className="text-[12px] text-primary hover:underline"
                      >
                        Complete
                      </button>
                    </>
                  ) : mine ? (
                    <button
                      onClick={async () => {
                        try {
                          await projectsApi.completeTask(task.id);
                          await onChanged();
                        } catch (err) {
                          alert(err.response?.data?.error?.message || 'Could not update task.');
                        }
                      }}
                      className="text-[12px] text-primary hover:underline"
                    >
                      Mark Complete
                    </button>
                  ) : (
                    taskStatusBadge(task.status)
                  )
                )}
              </div>
            </div>
          );
        })}
      </div>

      {showForm && (
        <TaskForm
          projectId={projectId} groups={groups} members={members} fixedGroupId={fixedGroupId}
          onClose={() => setShowForm(false)}
          onDone={async () => { setShowForm(false); await onChanged(); }}
        />
      )}
    </div>
  );
};

const TaskForm = ({ projectId, groups, members, fixedGroupId = '', onClose, onDone }) => {
  const [form, setForm] = useState({ title: '', description: '', priority: 'MEDIUM', due_at: '', group: fixedGroupId, assigned_student: '' });
  const [busy, setBusy] = useState(false);

  const submit = async (e) => {
    e.preventDefault();
    setBusy(true);
    const payload = {
      title: form.title,
      description: form.description,
      priority: form.priority,
      due_at: form.due_at ? new Date(form.due_at).toISOString() : null,
    };
    const group = fixedGroupId || form.group;
    if (group) payload.group = group;
    if (form.assigned_student) payload.assigned_student = form.assigned_student;
    try {
      await projectsApi.createTask(projectId, payload);
      await onDone();
    } catch (err) {
      alert(err.response?.data?.error?.message || 'Could not create task.');
      setBusy(false);
    }
  };

  return (
    <div className="fixed inset-0 bg-black/50 flex items-center justify-center z-50 p-4">
      <div className="bg-white rounded-xl shadow-xl max-w-lg w-full">
        <div className="flex items-center justify-between p-5 border-b border-border-default">
          <h3 className="text-[15px] font-bold text-text-primary">New Task</h3>
          <button onClick={onClose} className="p-1 hover:bg-page-bg rounded-lg"><X size={20} className="text-text-secondary" /></button>
        </div>
        <form onSubmit={submit} className="p-5 space-y-4">
          <div>
            <label className="fet-label">Title</label>
            <input type="text" value={form.title} onChange={(e) => setForm({ ...form, title: e.target.value })} required className="fet-input" />
          </div>
          <div>
            <label className="fet-label">Description</label>
            <textarea value={form.description} onChange={(e) => setForm({ ...form, description: e.target.value })} rows={2} className="fet-input resize-none" />
          </div>
          <div className="grid grid-cols-2 gap-4">
            <div>
              <label className="fet-label">Priority</label>
              <select value={form.priority} onChange={(e) => setForm({ ...form, priority: e.target.value })} className="fet-select">
                <option value="LOW">Low</option>
                <option value="MEDIUM">Medium</option>
                <option value="HIGH">High</option>
              </select>
            </div>
            <div>
              <label className="fet-label">Due</label>
              <input type="datetime-local" value={form.due_at} onChange={(e) => setForm({ ...form, due_at: e.target.value })} className="fet-input" />
            </div>
          </div>
          <div className={fixedGroupId ? '' : 'grid grid-cols-2 gap-4'}>
            {!fixedGroupId && (
              <div>
                <label className="fet-label">Group</label>
                <select value={form.group} onChange={(e) => setForm({ ...form, group: e.target.value })} className="fet-select">
                  <option value="">Unassigned</option>
                  {groups.map((g) => <option key={g.id} value={g.id}>{g.name}</option>)}
                </select>
              </div>
            )}
            <div>
              <label className="fet-label">Assignee</label>
              <select value={form.assigned_student} onChange={(e) => setForm({ ...form, assigned_student: e.target.value })} className="fet-select">
                <option value="">Unassigned</option>
                {members.map((m) => <option key={m.id} value={m.student}>{m.student_name}</option>)}
              </select>
            </div>
          </div>
          <div className="flex justify-end gap-3">
            <button type="button" onClick={onClose} className="fet-btn-secondary">Cancel</button>
            <button type="submit" className="fet-btn-primary" disabled={busy}>Create Task</button>
          </div>
        </form>
      </div>
    </div>
  );
};

const MilestonesTab = ({ projectId, milestones, canManage, onChanged }) => {
  const [showForm, setShowForm] = useState(false);
  const [editing, setEditing] = useState(null);

  const submit = async (m) => {
    try {
      if (editing) await projectsApi.updateMilestone(editing.id, m);
      else await projectsApi.createMilestone(projectId, m);
      setShowForm(false);
      setEditing(null);
      await onChanged();
    } catch (err) {
      alert(err.response?.data?.error?.message || 'Could not save milestone.');
    }
  };

  const toLocal = (iso) => {
    if (!iso) return '';
    const d = new Date(iso);
    if (Number.isNaN(d.getTime())) return '';
    const pad = (n) => String(n).padStart(2, '0');
    return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}T${pad(d.getHours())}:${pad(d.getMinutes())}`;
  };

  return (
    <div className="space-y-4">
      <div className="flex justify-between items-center">
        <h4 className="font-semibold text-text-primary">Milestones</h4>
        {canManage && (
          <button onClick={() => { setEditing(null); setShowForm(true); }} className="fet-btn-primary text-[13px] flex items-center gap-1">
            <Plus size={14} /> Add Milestone
          </button>
        )}
      </div>
      {milestones.length === 0 && <p className="text-center text-text-secondary py-6">No milestones for this project.</p>}
      <div className="space-y-3">
        {milestones.map((ms) => (
          <div key={ms.id} className="p-4 bg-page-bg rounded-lg">
            <div className="flex items-start justify-between gap-3">
              <div>
                <p className="font-medium text-text-primary text-[13px]">{ms.title}</p>
                <p className="text-[12px] text-text-secondary">{ms.description} {ms.due_at && `• Due: ${formatDateTime(ms.due_at)}`}</p>
              </div>
              <div className="flex items-center gap-3 flex-shrink-0">
                <span className={`fet-badge ${ms.status === 'COMPLETED' ? 'fet-badge-completed' : ms.status === 'IN_PROGRESS' ? 'fet-badge-pending' : 'fet-badge-inactive'}`}>
                  {ms.status?.replace('_', ' ') || 'PENDING'}
                </span>
                {canManage && (
                  <>
                    <button onClick={() => { setEditing(ms); setShowForm(true); }} className="text-[13px] text-primary hover:underline">Edit</button>
                    <button
                      onClick={async () => {
                        if (!window.confirm('Delete this milestone?')) return;
                        try {
                          await projectsApi.deleteMilestone(ms.id);
                          await onChanged();
                        } catch (err) {
                          alert(err.response?.data?.error?.message || 'Could not delete milestone.');
                        }
                      }}
                      className="text-[13px] text-red-500 hover:underline"
                    >
                      Delete
                    </button>
                  </>
                )}
              </div>
            </div>
          </div>
        ))}
      </div>

      {showForm && (
        <MilestoneForm
          milestone={editing}
          initialDue={toLocal(editing?.due_at)}
          onClose={() => { setShowForm(false); setEditing(null); }}
          onSubmit={submit}
        />
      )}
    </div>
  );
};

const MilestoneForm = ({ milestone, initialDue, onClose, onSubmit }) => {
  const [title, setTitle] = useState(milestone?.title || '');
  const [description, setDescription] = useState(milestone?.description || '');
  const [due_at, setDueAt] = useState(initialDue || '');
  const [status, setStatus] = useState(milestone?.status || 'PENDING');
  const [busy, setBusy] = useState(false);

  const submit = async (e) => {
    e.preventDefault();
    setBusy(true);
    await onSubmit({
      title,
      description,
      due_at: due_at ? new Date(due_at).toISOString() : null,
      status,
    });
    setBusy(false);
  };

  return (
    <div className="fixed inset-0 bg-black/50 flex items-center justify-center z-50 p-4">
      <div className="bg-white rounded-xl shadow-xl max-w-md w-full">
        <div className="flex items-center justify-between p-5 border-b border-border-default">
          <h3 className="text-[15px] font-bold text-text-primary">{milestone ? 'Edit Milestone' : 'Add Milestone'}</h3>
          <button onClick={onClose} className="p-1 hover:bg-page-bg rounded-lg"><X size={20} className="text-text-secondary" /></button>
        </div>
        <form onSubmit={submit} className="p-5 space-y-4">
          <div>
            <label className="fet-label">Title</label>
            <input type="text" value={title} onChange={(e) => setTitle(e.target.value)} required className="fet-input" />
          </div>
          <div>
            <label className="fet-label">Description</label>
            <textarea value={description} onChange={(e) => setDescription(e.target.value)} rows={2} className="fet-input resize-none" />
          </div>
          <div className="grid grid-cols-2 gap-4">
            <div>
              <label className="fet-label">Due</label>
              <input type="datetime-local" value={due_at} onChange={(e) => setDueAt(e.target.value)} className="fet-input" />
            </div>
            <div>
              <label className="fet-label">Status</label>
              <select value={status} onChange={(e) => setStatus(e.target.value)} className="fet-select">
                <option value="PENDING">Pending</option>
                <option value="IN_PROGRESS">In Progress</option>
                <option value="COMPLETED">Completed</option>
              </select>
            </div>
          </div>
          <div className="flex justify-end gap-3">
            <button type="button" onClick={onClose} className="fet-btn-secondary">Cancel</button>
            <button type="submit" className="fet-btn-primary" disabled={busy}>{milestone ? 'Update' : 'Add'}</button>
          </div>
        </form>
      </div>
    </div>
  );
};

const DocumentsTab = ({ documents }) => (
  <div className="space-y-4">
    <h4 className="font-semibold text-text-primary">Project Documents</h4>
    {documents.length === 0 && (
      <div className="text-center py-8">
        <FileText size={36} className="mx-auto text-text-secondary opacity-40 mb-2" />
        <p className="text-text-secondary text-[13px]">No documents uploaded yet.</p>
      </div>
    )}
    <div className="space-y-2">
      {documents.map((doc) => (
        <div key={doc.id} className="flex items-center justify-between p-3 bg-page-bg rounded-lg">
          <div className="flex items-center gap-2">
            <FileText size={16} className="text-primary flex-shrink-0" />
            <div>
              <p className="text-[13px] font-medium text-text-primary capitalize">{doc.document_type?.replace('_', ' ').toLowerCase()}</p>
              <p className="text-[11px] text-text-secondary">Uploaded {formatDateTime(doc.created_at)}</p>
            </div>
          </div>
          <span className="fet-badge fet-badge-inactive">{doc.file ? 'Attached' : 'Reference'}</span>
        </div>
      ))}
    </div>
  </div>
);

const ActivityTab = ({ projectId, contributions, onChanged }) => {
  const [showForm, setShowForm] = useState(false);
  const [description, setDescription] = useState('');
  const [type, setType] = useState('TASK_COMPLETION');
  const [busy, setBusy] = useState(false);

  const submit = async (e) => {
    e.preventDefault();
    setBusy(true);
    try {
      await projectsApi.createContribution(projectId, { description, contribution_type: type });
      setDescription('');
      setType('TASK_COMPLETION');
      setShowForm(false);
      await onChanged();
    } catch (err) {
      alert(err.response?.data?.error?.message || 'Could not log contribution.');
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="space-y-4">
      <div className="flex justify-between items-center">
        <h4 className="font-semibold text-text-primary">Contributions</h4>
        <button onClick={() => setShowForm(!showForm)} className="fet-btn-primary text-[13px] flex items-center gap-1">
          <Plus size={14} /> Log Contribution
        </button>
      </div>
      {contributions.length === 0 && <p className="text-center text-text-secondary py-6">No contributions logged yet.</p>}
      <div className="space-y-2">
        {contributions.map((c) => (
          <div key={c.id} className="flex items-start justify-between gap-3 p-3 bg-page-bg rounded-lg">
            <div className="min-w-0">
              <p className="text-[13px] font-medium text-text-primary">{c.student_name}</p>
              <p className="text-[12px] text-text-secondary">{c.description || '(no description)'}</p>
            </div>
            <div className="flex items-center gap-2 flex-shrink-0">
              <span className="fet-badge fet-badge-pending">{c.contribution_type?.replace('_', ' ')}</span>
              <span className="text-[11px] text-text-secondary">{new Date(c.created_at).toLocaleDateString()}</span>
            </div>
          </div>
        ))}
      </div>

      {showForm && (
        <form onSubmit={submit} className="p-4 bg-page-bg rounded-xl space-y-3">
          <div>
            <label className="fet-label">What did you contribute?</label>
            <textarea value={description} onChange={(e) => setDescription(e.target.value)} required rows={2} className="fet-input resize-none" />
          </div>
          <div className="flex items-center gap-3">
            <select value={type} onChange={(e) => setType(e.target.value)} className="fet-select flex-1">
              <option value="TASK_COMPLETION">Task Completion</option>
              <option value="CODE_CONTRIBUTION">Code</option>
              <option value="DOCUMENTATION">Documentation</option>
              <option value="RESEARCH">Research</option>
              <option value="DESIGN">Design</option>
              <option value="OTHER">Other</option>
            </select>
            <button type="submit" className="fet-btn-primary" disabled={busy}>Submit</button>
          </div>
        </form>
      )}
    </div>
  );
};

const AssessmentsTab = ({ projectId, assessments, members, canManage, onChanged }) => {
  const [showForm, setShowForm] = useState(false);
  const [name, setName] = useState('');
  const [maximum, setMaximum] = useState('100');
  const [weight, setWeight] = useState('1');
  const [scoring, setScoring] = useState(null);
  const [scores, setScores] = useState({});

  const createComponent = async (e) => {
    e.preventDefault();
    try {
      await projectsApi.createAssessment(projectId, { name, maximum_score: maximum, weight });
      setName('');
      setMaximum('100');
      setWeight('1');
      setShowForm(false);
      await onChanged();
    } catch (err) {
      alert(err.response?.data?.error?.message || 'Could not create assessment.');
    }
  };

  const record = async (componentId) => {
    try {
      await projectsApi.recordAssessment(componentId, {
        student: scoring.student,
        score: scores[componentId]?.score,
        feedback: scores[componentId]?.feedback || '',
      });
      setScoring(null);
      await onChanged();
    } catch (err) {
      alert(err.response?.data?.error?.message || 'Could not record score.');
    }
  };

  return (
    <div className="space-y-4">
      <div className="flex justify-between items-center">
        <h4 className="font-semibold text-text-primary">Assessments</h4>
        {canManage && (
          <button onClick={() => setShowForm(!showForm)} className="fet-btn-primary text-[13px] flex items-center gap-1">
            <Plus size={14} /> Add Component
          </button>
        )}
      </div>

      {showForm && (
        <form onSubmit={createComponent} className="p-4 bg-page-bg rounded-xl grid grid-cols-1 sm:grid-cols-4 gap-3">
          <div className="sm:col-span-2">
            <label className="fet-label">Component Name</label>
            <input type="text" value={name} onChange={(e) => setName(e.target.value)} required className="fet-input" placeholder="e.g. Code quality" />
          </div>
          <div>
            <label className="fet-label">Max Score</label>
            <input type="number" value={maximum} onChange={(e) => setMaximum(e.target.value)} required className="fet-input" />
          </div>
          <div>
            <label className="fet-label">Weight</label>
            <input type="number" value={weight} onChange={(e) => setWeight(e.target.value)} required className="fet-input" />
          </div>
          <div className="sm:col-span-4 flex justify-end">
            <button type="submit" className="fet-btn-primary text-[13px]">Create Component</button>
          </div>
        </form>
      )}

      {assessments.length === 0 && <p className="text-center text-text-secondary py-6">No assessment components.</p>}

      <div className="space-y-3">
        {assessments.map((a) => (
          <div key={a.id} className="p-4 bg-page-bg rounded-lg border border-border-default">
            <div className="flex items-center justify-between gap-3">
              <div>
                <p className="font-medium text-text-primary text-[13px]">{a.name}</p>
                <p className="text-[12px] text-text-secondary">{a.description} • Max {a.maximum_score} • Weight {a.weight}</p>
              </div>
              {canManage && members.length > 0 && (
                <button onClick={() => setScoring(a)} className="fet-btn-secondary text-[12px] px-3 py-1.5 flex items-center gap-1">
                  <ClipboardCheck size={14} /> Record
                </button>
              )}
            </div>
            {scoring && scoring.id === a.id && (
              <ScoreForm
                component={a}
                members={members}
                value={scores[a.id] || {}}
                onChange={(patch) => setScores({ ...scores, [a.id]: { ...scores[a.id], ...patch } })}
                onCancel={() => setScoring(null)}
                onSave={() => record(a.id)}
              />
            )}
          </div>
        ))}
      </div>
    </div>
  );
};

const ScoreForm = ({ component, members, value, onChange, onCancel, onSave }) => (
  <div className="mt-4 p-3 bg-white rounded-xl grid grid-cols-1 sm:grid-cols-3 gap-3 items-end">
    <div>
      <label className="fet-label">Student</label>
      <select value={value.student || ''} onChange={(e) => onChange({ student: e.target.value })} className="fet-select">
        <option value="">Select...</option>
        {members.map((m) => <option key={m.id} value={m.student}>{m.student_name}</option>)}
      </select>
    </div>
    <div>
      <label className="fet-label">Score / {component.maximum_score}</label>
      <input type="number" step="0.01" value={value.score || ''} onChange={(e) => onChange({ score: e.target.value })} className="fet-input" />
    </div>
    <div>
      <label className="fet-label">Feedback</label>
      <input type="text" value={value.feedback || ''} onChange={(e) => onChange({ feedback: e.target.value })} className="fet-input" />
    </div>
    <div className="sm:col-span-3 flex justify-end gap-2">
      <button onClick={onCancel} className="fet-btn-secondary text-[13px]">Cancel</button>
      <button onClick={onSave} disabled={!value.student} className="fet-btn-primary text-[13px]">Save Score</button>
    </div>
  </div>
);

const ReportModal = ({ report, onClose }) => {
  const s = report.summary || {};
  return (
    <div className="fixed inset-0 bg-black/50 flex items-center justify-center z-50 p-4">
      <div className="bg-white rounded-xl shadow-xl max-w-2xl w-full max-h-[90vh] overflow-y-auto">
        <div className="flex items-center justify-between p-5 border-b border-border-default">
          <h3 className="text-[15px] font-bold text-text-primary">
            {report.project?.title} — {report.group?.name}
          </h3>
          <button onClick={onClose} className="p-1 hover:bg-page-bg rounded-lg"><X size={20} className="text-text-secondary" /></button>
        </div>
        <div className="p-5 space-y-5">
          <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
            {[
              ['Members', s.member_count],
              ['Completion', `${s.completion_rate}%`],
              ['Tasks', `${s.completed_tasks}/${s.total_tasks}`],
              ['Contributions', s.contribution_count],
            ].map(([label, value]) => (
              <div key={label} className="p-3 bg-page-bg rounded-lg text-center">
                <p className="text-[18px] font-bold text-text-primary">{value}</p>
                <p className="text-[11px] text-text-secondary mt-1">{label}</p>
              </div>
            ))}
          </div>
          <div>
            <h4 className="font-semibold text-text-primary mb-2 text-[13px]">Member Breakdown</h4>
            <div className="space-y-2">
              {(report.members || []).map((m) => (
                <div key={m.member_id} className="flex items-center justify-between p-3 bg-page-bg rounded-lg">
                  <div>
                    <p className="text-[13px] font-medium text-text-primary">{m.student_name}</p>
                    <p className="text-[11px] text-text-secondary">{m.role === 'GROUP_LEADER' ? 'Group Leader' : 'Member'} • {m.email}</p>
                  </div>
                  <div className="flex gap-4 text-[12px] text-text-secondary">
                    <span>Tasks {m.tasks_completed}/{m.tasks_assigned}</span>
                    <span>Contribs {m.contributions}</span>
                  </div>
                </div>
              ))}
            </div>
          </div>
          <div>
            <h4 className="font-semibold text-text-primary mb-2 text-[13px]">Tasks</h4>
            <div className="space-y-2">
              {(report.tasks || []).map((t) => (
                <div key={t.id} className="flex items-center justify-between p-3 bg-page-bg rounded-lg">
                  <p className="text-[13px] text-text-primary">{t.title}</p>
                  {taskStatusBadge(t.status)}
                </div>
              ))}
            </div>
          </div>
        </div>
      </div>
    </div>
  );
};

export default ProjectDetails;