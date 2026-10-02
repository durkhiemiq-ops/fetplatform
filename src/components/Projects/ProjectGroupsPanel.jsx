import React, { useState, useEffect, useCallback } from 'react';
import {
  Users, UserPlus, Trash2, Crown, AlertCircle, RefreshCw, Loader2,
  UserCheck, FolderKanban, ChevronDown, ChevronUp, Search, X, Info,
} from 'lucide-react';
import { projectsApi } from '../../lib/projects';
import { useSession } from '../../context/SessionContext';

const SCOPE_LABEL = {
  INDIVIDUAL: 'Individual',
  CLASS_WIDE: 'Class-wide',
  GROUP_SPECIFIC: 'Group project',
};

/**
 * The lecturer's view of one project: every group side by side, the students
 * who still need placing, and group management that a class delegate can also
 * perform. Students never see this panel -- the API refuses them.
 */
const ProjectGroupsPanel = ({ project, canManageGroups, canManageProject, onChanged }) => {
  const { role: sessionRole } = useSession();
  const role = sessionRole;
  const [groups, setGroups] = useState([]);
  const [unassigned, setUnassigned] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [busy, setBusy] = useState(false);
  const [showNewGroup, setShowNewGroup] = useState(false);
  const [newGroupName, setNewGroupName] = useState('');
  const [expanded, setExpanded] = useState({});
  const [moveTarget, setMoveTarget] = useState({}); // studentId -> groupId
  const [search] = useState('');

  const load = useCallback(async () => {
    setLoading(true);
    setError('');
    try {
      const g = await projectsApi.listGroups(project.id);
      setGroups(Array.isArray(g) ? g : []);
      if (canManageGroups) {
        const u = await projectsApi.unassigned(project.id);
        setUnassigned(Array.isArray(u) ? u : []);
      } else {
        setUnassigned([]);
      }
    } catch (err) {
      setError(err.response?.data?.error?.message || 'Could not load groups.');
    } finally {
      setLoading(false);
    }
  }, [project.id, canManageGroups]);

  useEffect(() => { load(); }, [load]);

  const createGroup = async (e) => {
    e.preventDefault();
    const name = newGroupName.trim();
    if (!name) return;
    setBusy(true);
    setError('');
    try {
      await projectsApi.createGroup(project.id, { name });
      setNewGroupName('');
      setShowNewGroup(false);
      await load();
      if (onChanged) onChanged();
    } catch (err) {
      setError(err.response?.data?.error?.message || 'Could not create the group.');
    } finally {
      setBusy(false);
    }
  };

  const deleteGroup = async (group) => {
    if (!window.confirm(`Delete "${group.name}"? Its members stay in the project but lose this group.`)) return;
    setBusy(true);
    setError('');
    try {
      await projectsApi.deleteGroup(project.id, group.id);
      await load();
      if (onChanged) onChanged();
    } catch (err) {
      setError(err.response?.data?.error?.message || 'Could not delete the group.');
    } finally {
      setBusy(false);
    }
  };

  const moveStudent = async (studentId, groupId) => {
    setMoveTarget((p) => ({ ...p, [studentId]: groupId }));
    setError('');
    try {
      if (groupId) {
        await projectsApi.addMember(project.id, groupId, { student_id: studentId, role: 'MEMBER' });
      } else {
        const g = groups.find((x) => (x.members || []).some((m) => m.student === studentId));
        if (g) await projectsApi.removeMember(project.id, g.id, studentId);
      }
      await load();
      if (onChanged) onChanged();
    } catch (err) {
      setError(err.response?.data?.error?.message || 'Could not move that student.');
    } finally {
      setMoveTarget((p) => ({ ...p, [studentId]: '' }));
    }
  };

  const setLeader = async (group, studentId) => {
    setBusy(true);
    setError('');
    try {
      await projectsApi.updateGroup(project.id, group.id, { leader: studentId || null });
      await load();
    } catch (err) {
      setError(err.response?.data?.error?.message || 'Could not set the group leader.');
    } finally {
      setBusy(false);
    }
  };

  if (loading) {
    return (
      <div className="flex items-center justify-center gap-2 py-6 text-sm text-text-secondary">
        <Loader2 size={16} className="animate-spin" /> Loading groups...
      </div>
    );
  }

  const term = search.trim().toLowerCase();
  const matches = (s) => (
    !term
    || (s.full_name || '').toLowerCase().includes(term)
    || (s.student_number || '').toLowerCase().includes(term)
  );

  return (
    <div className="space-y-4">
      {error && (
        <div className="flex items-start gap-2 bg-red-50 border border-red-200 text-red-700 px-4 py-3 rounded-xl text-[13px]">
          <AlertCircle size={16} className="mt-0.5 shrink-0" />
          <span>{error}</span>
        </div>
      )}

      <div className="flex items-center justify-between flex-wrap gap-2">
        <div>
          <p className="text-sm font-medium text-text-primary flex items-center gap-2">
            <Users size={15} /> Groups
            <span className="text-xs font-normal text-text-secondary">({groups.length})</span>
          </p>
          <p className="text-xs text-text-secondary">
            {SCOPE_LABEL[project.scope] || project.scope}
            {project.group_name ? ` · ${project.group_name}` : ''}
          </p>
        </div>
        <div className="flex items-center gap-2">
          <button onClick={load} className="fet-btn-secondary text-xs" title="Refresh">
            <RefreshCw size={14} />
          </button>
          {canManageGroups && project.scope === 'CLASS_WIDE' && (
            <button onClick={() => setShowNewGroup((v) => !v)} className="fet-btn-primary text-xs">
              <UserPlus size={14} /> New group
            </button>
          )}
        </div>
      </div>

      {showNewGroup && (
        <form onSubmit={createGroup} className="flex items-center gap-2">
          <input
            autoFocus
            value={newGroupName}
            onChange={(e) => setNewGroupName(e.target.value)}
            placeholder="Group name, e.g. Team Phoenix"
            className="fet-input flex-1"
          />
          <button type="submit" disabled={busy || !newGroupName.trim()} className="fet-btn-primary text-sm">
            {busy ? <Loader2 size={14} className="animate-spin" /> : 'Create'}
          </button>
          <button type="button" onClick={() => setShowNewGroup(false)} className="fet-btn-secondary text-sm">
            <X size={14} />
          </button>
        </form>
      )}

      {/* Unassigned bucket */}
      {canManageGroups && (
        <div className="rounded-xl border border-amber-200 bg-amber-50/60 p-3">
          <p className="text-sm font-medium text-text-primary flex items-center gap-2">
            <UserCheck size={15} /> Unassigned
            <span className="text-xs font-normal text-text-secondary">({unassigned.length})</span>
          </p>
          {unassigned.length === 0 ? (
            <p className="text-xs text-text-secondary mt-1">
              Every enrolled student is in a group.
            </p>
          ) : (
            <>
              <p className="text-xs text-text-secondary mt-1 mb-2">
                These students have not joined a group yet.
              </p>
              <div className="flex flex-wrap gap-2">
                {unassigned.filter(matches).map((s) => (
                  <div
                    key={s.id}
                    className="flex items-center gap-2 bg-white border border-border-default rounded-lg px-2 py-1"
                  >
                    <span className="text-xs">
                      <span className="font-medium text-text-primary">{s.full_name}</span>
                      <span className="text-text-secondary"> · {s.student_number || 'no matricule'}</span>
                    </span>
                    <select
                      value={moveTarget[s.id] || ''}
                      onChange={(e) => moveStudent(s.id, e.target.value)}
                      className="text-xs border border-border-default rounded px-1 py-0.5 bg-white"
                    >
                      <option value="">Add to...</option>
                      {groups.map((g) => (
                        <option key={g.id} value={g.id}>{g.name}</option>
                      ))}
                    </select>
                  </div>
                ))}
                {unassigned.filter(matches).length === 0 && (
                  <p className="text-xs text-text-secondary">No unassigned student matches “{search}”.</p>
                )}
              </div>
            </>
          )}
        </div>
      )}

      {groups.length === 0 ? (
        <div className="text-center py-6 text-text-secondary text-[13px] flex flex-col items-center gap-2">
          <FolderKanban size={32} className="opacity-50" />
          {project.scope === 'CLASS_WIDE'
            ? (canManageGroups
              ? 'No groups yet. Create the first one, or let the class delegate do it.'
              : 'No groups have been formed yet.')
            : 'This project has no groups.'}
        </div>
      ) : (
        <div className="space-y-2">
          {groups.map((g) => {
            const isOpen = expanded[g.id];
            const members = (g.members || []).filter(matches);
            return (
              <div key={g.id} className="rounded-xl border border-border-default bg-white overflow-hidden">
                <div className="flex items-center justify-between gap-2 p-3">
                  <button
                    onClick={() => setExpanded((p) => ({ ...p, [g.id]: !p[g.id] }))}
                    className="flex items-center gap-2 text-left min-w-0"
                  >
                    {isOpen ? <ChevronUp size={15} /> : <ChevronDown size={15} />}
                    <span className="min-w-0">
                      <span className="block text-sm font-medium text-text-primary truncate">{g.name}</span>
                      <span className="block text-xs text-text-secondary">
                        {g.member_count} member{g.member_count === 1 ? '' : 's'}
                        {g.leader_name ? ` · led by ${g.leader_name}` : ''}
                        {' · '}
                        {g.completed_task_count}/{g.task_count} tasks done
                      </span>
                    </span>
                  </button>
                  {canManageGroups && (
                    <button
                      onClick={() => deleteGroup(g)}
                      disabled={busy}
                      className="p-1.5 rounded-lg text-text-secondary hover:text-danger hover:bg-red-50"
                      title="Delete group"
                    >
                      <Trash2 size={15} />
                    </button>
                  )}
                </div>

                {isOpen && (
                  <div className="border-t border-border-default p-3 space-y-2">
                    {members.length === 0 ? (
                      <p className="text-xs text-text-secondary">No members.</p>
                    ) : (
                      <div className="space-y-1">
                        {members.map((m) => (
                          <div key={m.id} className="flex items-center justify-between gap-2 text-sm">
                            <span className="flex items-center gap-2 min-w-0">
                              {m.role === 'GROUP_LEADER'
                                ? <Crown size={13} className="text-amber-500 shrink-0" />
                                : <span className="w-[13px] shrink-0" />}
                              <span className="truncate">{m.student_name}</span>
                            </span>
                            {canManageGroups && (
                              <div className="flex items-center gap-2">
                                <select
                                  value={moveTarget[m.student] || ''}
                                  onChange={(e) => moveStudent(m.student, e.target.value)}
                                  className="text-xs border border-border-default rounded px-1 py-0.5"
                                >
                                  <option value="">Move to...</option>
                                  {groups.filter((x) => x.id !== g.id).map((x) => (
                                    <option key={x.id} value={x.id}>{x.name}</option>
                                  ))}
                                </select>
                                {m.role === 'GROUP_LEADER' ? (
                                  <button
                                    onClick={() => setLeader(g, '')}
                                    className="text-xs text-text-secondary hover:underline"
                                  >
                                    Unset lead
                                  </button>
                                ) : (
                                  <button
                                    onClick={() => setLeader(g, m.student)}
                                    className="text-xs text-primary hover:underline"
                                  >
                                    Make lead
                                  </button>
                                )}
                              </div>
                            )}
                          </div>
                        ))}
                      </div>
                    )}

                    {g.assigned_projects?.length > 0 && (
                      <div className="pt-2 mt-2 border-t border-border-default">
                        <p className="text-xs font-medium text-text-secondary mb-1">Assigned project(s)</p>
                        {g.assigned_projects.map((p) => (
                          <p key={p.id} className="text-xs text-text-primary">• {p.title}</p>
                        ))}
                      </div>
                    )}
                  </div>
                )}
              </div>
            );
          })}
        </div>
      )}

      {canManageGroups && project.scope === 'CLASS_WIDE' && (
        <p className="text-[11px] text-text-secondary flex items-start gap-1">
          <Info size={12} className="mt-0.5 shrink-0" />
          {role === 'lecturer'
            ? 'The class delegate can also create groups and move students, but cannot edit this project or enter marks.'
            : 'You can manage groups for this project, but not the project settings or marks.'}
        </p>
      )}
    </div>
  );
};

export default ProjectGroupsPanel;
