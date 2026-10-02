import React, { useState, useEffect, useCallback } from 'react';
import { useNavigate } from 'react-router-dom';
import { Plus, Search, X, FolderKanban, RefreshCw, AlertCircle, Users, Layers, User } from 'lucide-react';
import { projectsApi } from '../../lib/projects';
import { attendanceApi } from '../../lib/attendance';
import { useSession } from '../../context/SessionContext';
import ProjectCard from './ProjectCard';
import ProjectForm from './ProjectForm';
import { STATUS_LABELS } from './projectUi';
import ProjectGroupsPanel from './ProjectGroupsPanel';
import ClassDelegateControl from './ClassDelegateControl';
import {
  SectionHeader, Card, CardBody, CardFoot, Eyebrow, Pill, Tag, Callout, EmptyState, Bar,
} from '../UI';

const STATUS_OPTIONS = { ALL: 'All Projects', ...STATUS_LABELS };
const SCOPE_FILTERS = {
  ALL: 'Any scope',
  INDIVIDUAL: 'Individual',
  CLASS_WIDE: 'Class-wide (grouped)',
  GROUP_SPECIFIC: 'Assigned to a group',
};
const SCOPE_ICON = { INDIVIDUAL: User, CLASS_WIDE: Users, GROUP_SPECIFIC: Layers };

const ProjectsList = () => {
  const navigate = useNavigate();
  // Role comes from the verified session, not localStorage (AGENTS.md).
  const { isStaff, isAdmin } = useSession();
  const canManage = isStaff;

  const [projects, setProjects] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [searchTerm, setSearchTerm] = useState('');
  const [filter, setFilter] = useState('ALL');
  const [scopeFilter, setScopeFilter] = useState('ALL');
  const [showForm, setShowForm] = useState(false);
  const [editingProject, setEditingProject] = useState(null);
  const [courses, setCourses] = useState([]);
  const [groupOptions, setGroupOptions] = useState([]);
  const [saving, setSaving] = useState(false);
  const [expandedId, setExpandedId] = useState(null);

  const load = useCallback(async () => {
    setLoading(true);
    setError('');
    try {
      const data = await projectsApi.listProjects();
      setProjects(Array.isArray(data) ? data : []);
    } catch (err) {
      setError(err.response?.data?.error?.message || 'Failed to load projects.');
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  // Groups across every course the lecturer teaches, needed when assigning a
  // project to a group.
  const loadGroupOptions = async (offeringId) => {
    try {
      const g = await projectsApi.offeringGroups(offeringId);
      setGroupOptions(Array.isArray(g) ? g : []);
    } catch {
      setGroupOptions([]);
    }
  };

  const openForm = async (project) => {
    if (!project && canManage && courses.length === 0) {
      try {
        setCourses(await attendanceApi.lecturerCourses());
      } catch {
        /* list stays empty */
      }
    }
    setEditingProject(project);
    setShowForm(true);
    if (!project) { setGroupOptions([]); }
  };

  const handleOfferingChange = async (offeringId) => {
    if (offeringId) await loadGroupOptions(offeringId);
    else setGroupOptions([]);
  };

  const handleSave = async (payload, project) => {
    setSaving(true);
    setError('');
    try {
      if (project) {
        await projectsApi.updateProject(project.id, payload);
      } else {
        await projectsApi.createProject(payload);
      }
      setShowForm(false);
      setEditingProject(null);
      await load();
      if (!project && canManage) navigate('/projects');
    } catch (err) {
      setError(err.response?.data?.error?.message || 'Could not save the project.');
    } finally {
      setSaving(false);
    }
  };

  const filtered = projects.filter((p) => {
    const q = searchTerm.toLowerCase();
    const matchesSearch =
      (p.title || '').toLowerCase().includes(q) ||
      (p.course_code || '').toLowerCase().includes(q) ||
      (p.supervisor_name || '').toLowerCase().includes(q);
    const matchesFilter = filter === 'ALL' || p.status === filter;
    const matchesScope = scopeFilter === 'ALL' || p.scope === scopeFilter;
    return matchesSearch && matchesFilter && matchesScope;
  });

  const counts = {
    total: projects.length,
    active: projects.filter((p) => p.status === 'ACTIVE').length,
    completed: projects.filter((p) => p.status === 'COMPLETED').length,
    draft: projects.filter((p) => p.status === 'DRAFT').length,
  };

  return (
    <div className="space-y-4">
      <SectionHeader
        area="projects"
        icon={FolderKanban}
        title="Projects"
        subtitle="Work can be individual, shared by the whole class, or given to one group. All three run at the same time."
        crumb={[{ label: 'FET Platform' }, { label: 'Projects' }]}
        actions={canManage ? (
          <button type="button" onClick={() => openForm(null)} className="fet-btn-primary">
            <Plus size={15} /> New project
          </button>
        ) : null}
      />

      {error && (
        <Callout tone="bd" icon={AlertCircle}>{error}</Callout>
      )}

      <div className="grid grid-cols-2 sm:grid-cols-4 gap-4">
        {[
          ['Total', counts.total],
          ['Active', counts.active],
          ['Completed', counts.completed],
          ['Draft', counts.draft],
        ].map(([label, value]) => (
          <div key={label} className="fet-card p-4 text-center">
            <p className="text-[22px] font-bold text-text-primary">{value}</p>
            <p className="text-[12px] font-medium text-text-secondary mt-1">{label}</p>
          </div>
        ))}
      </div>

        <div className="flex flex-col gap-4 sm:flex-row sm:items-center">
          <div className="relative flex-1">
            <Search className="absolute left-3 top-1/2 -translate-y-1/2 text-text-muted" size={16} />
            <input
              type="text"
              placeholder="Search by title, course or supervisor"
              value={searchTerm}
              onChange={(e) => setSearchTerm(e.target.value)}
              className="fet-input pl-9"
            />
          </div>
          <select value={filter} onChange={(e) => setFilter(e.target.value)} className="fet-select sm:w-44">
            {Object.entries(STATUS_OPTIONS).map(([value, label]) => (
              <option key={value} value={value}>{label}</option>
            ))}
          </select>
          <select value={scopeFilter} onChange={(e) => setScopeFilter(e.target.value)} className="fet-select sm:w-48">
            {Object.entries(SCOPE_FILTERS).map(([value, label]) => (
              <option key={value} value={value}>{label}</option>
            ))}
          </select>
          <button type="button" onClick={load} className="fet-btn-secondary" title="Refresh">
            <RefreshCw size={15} />
          </button>
        </div>

      {loading ? (
        <Card accent="projects">
          <EmptyState icon={RefreshCw} title="Loading projects" subtitle="Fetching the projects you can see." />
        </Card>
      ) : (
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
          {filtered.map((project) => {
            const ScopeIcon = SCOPE_ICON[project.scope] || FolderKanban;
            const isOpen = expandedId === project.id;
            const canManageProject = canManage;
            const canManageGroups = canManage && (
              project.scope === 'CLASS_WIDE' || isAdmin
            );
            return (
              <div key={project.id} className="space-y-3">
                <ProjectCard project={project} />
                <div className="flex flex-wrap items-center gap-2 px-1">
                  <span className="ui-tag">
                    <ScopeIcon size={12} className="mr-1 inline align-[-1px]" />
                    {SCOPE_FILTERS[project.scope] || project.scope}
                    {project.group_name ? ` · ${project.group_name}` : ''}
                  </span>
                  {project.scope === 'CLASS_WIDE' && project.unassigned_count > 0 ? (
                    <Pill tone="wn">{project.unassigned_count} unassigned</Pill>
                  ) : null}
                  {canManage ? (
                    <button
                      type="button"
                      onClick={() => setExpandedId(isOpen ? null : project.id)}
                      className="ml-auto text-[11.5px] text-primary hover:underline"
                    >
                      {isOpen ? 'Hide groups' : 'Manage groups'}
                    </button>
                  ) : null}
                </div>
                {isOpen ? (
                  <div className="ui-card space-y-4 p-4">
                    {canManage && project.scope === 'CLASS_WIDE' ? (
                      <ClassDelegateControl offeringId={project.course_offering} canAppoint />
                    ) : null}
                    <ProjectGroupsPanel
                      project={project}
                      canManageGroups={canManageGroups}
                      canManageProject={canManageProject}
                      onChanged={load}
                    />
                  </div>
                ) : null}
              </div>
            );
          })}
        </div>
      )}

      {!loading && filtered.length === 0 ? (
        <Card accent="projects">
          <EmptyState
            icon={FolderKanban}
            title={projects.length === 0
              ? (canManage ? 'No projects yet' : 'No projects assigned to you yet')
              : 'No project matches your filters'}
            subtitle={projects.length === 0
              ? (canManage
                ? 'Create the first one to get started.'
                : 'Projects appear here once you are added to one.')
              : 'Try a different search, scope or status.'}
            action={projects.length === 0 && canManage ? (
              <button type="button" onClick={() => openForm(null)} className="fet-btn-primary">
                <Plus size={15} /> New project
              </button>
            ) : null}
          />
        </Card>
      ) : null}

      {showForm && (
        <div className="fixed inset-0 bg-black/50 flex items-center justify-center z-50 p-4">
          <div className="bg-white rounded-xl shadow-xl max-w-2xl w-full max-h-[90vh] overflow-y-auto">
            <div className="flex items-center justify-between p-6 border-b border-border-default">
              <h3 className="text-[15px] font-bold text-text-primary">
                {editingProject ? 'Edit Project' : 'Create New Project'}
              </h3>
              <button
                onClick={() => { setShowForm(false); setEditingProject(null); setError(''); }}
                className="p-1 hover:bg-page-bg rounded-lg transition-colors"
              >
                <X size={20} className="text-text-secondary" />
              </button>
            </div>
            <div className="p-6">
              <ProjectForm
                project={editingProject}
                courses={courses}
                groupOptions={groupOptions}
                onOfferingChange={handleOfferingChange}
                onClose={() => { setShowForm(false); setEditingProject(null); setError(''); setGroupOptions([]); }}
                onSave={handleSave}
                saving={saving}
              />
            </div>
          </div>
        </div>
      )}
    </div>
  );
};

export default ProjectsList;