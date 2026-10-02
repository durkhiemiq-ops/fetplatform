import React, { useState, useMemo } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import { useAppContext } from '../../context/AppContext';
import { ArrowLeft, Users, CheckSquare, Target, Plus, X } from 'lucide-react';
import { taskStatusLabel } from '../../utils/mappers';

const ProjectDetails = () => {
  const { id } = useParams();
  const navigate = useNavigate();
  const { projects, tasks, milestones, groups, memberships, updateProject, addMilestone, updateMilestone, deleteMilestone, capabilities } = useAppContext();
  const [activeTab, setActiveTab] = useState('overview');
  const [showMilestoneForm, setShowMilestoneForm] = useState(false);
  const [editingMilestone, setEditingMilestone] = useState(null);
  const [error, setError] = useState('');

  // H5: project ids are UUIDs. parseInt() on a UUID is always NaN, so the old
  // lookup could never find the project. And children join on the project UUID
  // (`project` FK), never on the project title.
  const project = projects.find((p) => p.id === id);
  const projectTasks = tasks.filter((t) => t.project === id);
  const projectMilestones = milestones.filter((m) => m.projectId === id);
  const projectGroups = groups.filter((g) => g.projectId === id);
  const projectMembers = memberships.filter((m) => m.projectId === id);

  const tabs = ['Overview', 'Tasks', 'Milestones', 'Groups'];

  const handleMilestoneSubmit = async (e) => {
    e.preventDefault();
    setError('');
    const formData = new FormData(e.target);
    const milestoneData = {
      title: formData.get('title'),
      projectId: id,
      progress: parseInt(formData.get('progress'), 10) || 0,
      dueDate: formData.get('dueDate') || null,
    };
    try {
      if (editingMilestone) {
        await updateMilestone(editingMilestone.id, milestoneData);
      } else {
        await addMilestone(milestoneData);
      }
      setShowMilestoneForm(false);
      setEditingMilestone(null);
    } catch (err) {
      setError(err.message || 'Could not save the milestone.');
    }
  };

  // Progress is derived from milestones — Project has no progress column.
  const milestoneProgress = projectMilestones.length
    ? Math.round(
        projectMilestones.reduce((sum, m) => sum + (m.progress || 0), 0) / projectMilestones.length
      )
    : null;

  if (!project) {
    return (
      <div className="text-center py-12">
        <h2 className="text-[22px] font-bold text-text-primary">Project not found</h2>
        <button onClick={() => navigate('/projects')} className="mt-4 text-primary hover:underline">
          Back to Projects
        </button>
      </div>
    );
  }

  return (
    <div className="space-y-6">
      <button 
        onClick={() => navigate('/projects')}
        className="flex items-center gap-2 text-text-secondary hover:text-text-primary transition-colors"
      >
        <ArrowLeft size={18} />
        <span>Back to Projects</span>
      </button>

      <div className="fet-card p-6">
        <div className="flex items-start justify-between mb-6">
          <div>
            <span className={`fet-badge mb-2 ${
              project.status === 'active'
                ? 'fet-badge-active'
                : project.status === 'archived'
                ? 'fet-badge-inactive'
                : 'fet-badge-warning'
            }`}>
              {project.status || 'draft'}
            </span>
            <h2 className="text-[22px] font-bold text-text-primary">{project.title}</h2>
          </div>
          {/* H5: Project has no progress/deadline column. Milestone progress is
              the only real signal, so it is shown instead of a 0% bar. */}
          <div className="text-right">
            <p className="text-[13px] text-text-secondary">Milestone progress</p>
            <p className="text-[22px] font-bold text-text-primary">
              {milestoneProgress == null ? '—' : `${milestoneProgress}%`}
            </p>
          </div>
        </div>

        {milestoneProgress != null && (
          <div className="fet-progress-bar mb-6">
            <div className="fet-progress-bar-fill" style={{ width: `${milestoneProgress}%` }} />
          </div>
        )}

        {error && (
          <div className="mb-4 rounded-lg border border-red-200 bg-red-50 px-4 py-2.5 text-[13px] text-red-700">
            {error}
          </div>
        )}

        <div className="flex gap-4 border-b border-border-default mb-6 overflow-x-auto">
          {tabs.map((tab) => (
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

        {/* Overview Tab */}
        {activeTab === 'overview' && (
          <div className="space-y-6">
            {/* H5: Project has no description column — render the real facts. */}
            <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
              <div className="p-4 bg-page-bg rounded-lg">
                <p className="text-[13px] text-text-secondary">Owner</p>
                <p className="font-medium text-text-primary">{project.ownerName || '—'}</p>
              </div>
              <div className="p-4 bg-page-bg rounded-lg">
                <p className="text-[13px] text-text-secondary">Supervisor</p>
                <p className="font-medium text-text-primary">{project.supervisorName || 'Not assigned'}</p>
              </div>
              <div className="p-4 bg-page-bg rounded-lg">
                <p className="text-[13px] text-text-secondary">Created</p>
                <p className="font-medium text-text-primary">
                  {project.created_at ? new Date(project.created_at).toLocaleDateString() : '—'}
                </p>
              </div>
              <div className="p-4 bg-page-bg rounded-lg">
                <p className="text-[13px] text-text-secondary">Members</p>
                <p className="font-medium text-text-primary">{projectMembers.length}</p>
              </div>
            </div>

            <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
              <div className="p-4 bg-page-bg rounded-lg text-center">
                <Users size={20} className="mx-auto text-primary mb-2" />
                <p className="text-[13px] text-text-secondary">Groups</p>
                <p className="text-xl font-bold text-text-primary">{projectGroups.length}</p>
              </div>
              <div className="p-4 bg-page-bg rounded-lg text-center">
                <CheckSquare size={20} className="mx-auto text-primary mb-2" />
                <p className="text-[13px] text-text-secondary">Tasks</p>
                <p className="text-xl font-bold text-text-primary">{projectTasks.length}</p>
              </div>
              <div className="p-4 bg-page-bg rounded-lg text-center">
                <Target size={20} className="mx-auto text-primary mb-2" />
                <p className="text-[13px] text-text-secondary">Milestones</p>
                <p className="text-xl font-bold text-text-primary">{projectMilestones.length}</p>
              </div>
            </div>
          </div>
        )}

        {/* Tasks Tab */}
        {activeTab === 'tasks' && (
          <div>
            {projectTasks.length > 0 ? (
              <div className="space-y-2">
                {projectTasks.map(task => (
                  <div key={task.id} className="flex items-center justify-between p-3 bg-page-bg rounded-lg">
                    <div>
                      <p className="font-medium text-text-primary">{task.title}</p>
                      {/* H5: ProjectTask has no due_date column; show the assignee. */}
                      <p className="text-[13px] text-text-secondary">
                        {task.assigneeName ? `Assigned to ${task.assigneeName}` : 'Unassigned'}
                      </p>
                    </div>
                    <span className={`fet-badge ${
                      task.status === 'completed' ? 'fet-badge-completed' :
                      task.status === 'in_progress' ? 'fet-badge-pending' :
                      'fet-badge-inactive'
                    }`}>
                      {taskStatusLabel(task.status)}
                    </span>
                  </div>
                ))}
              </div>
            ) : (
              <p className="text-center text-text-secondary py-8">No tasks for this project</p>
            )}
          </div>
        )}

        {/* Milestones Tab */}
        {activeTab === 'milestones' && (
          <div>
            <div className="flex justify-between items-center mb-4">
              <h4 className="font-semibold text-text-primary">Milestones</h4>
              <button 
                onClick={() => setShowMilestoneForm(true)}
                className="flex items-center gap-1 text-[13px] text-primary hover:underline"
              >
                <Plus size={16} />
                Add Milestone
              </button>
            </div>
            {projectMilestones.length > 0 ? (
              <div className="space-y-3">
                {projectMilestones.map(milestone => (
                  <div key={milestone.id} className="p-4 bg-page-bg rounded-lg">
                    <div className="flex items-start justify-between">
                      <div>
                        <p className="font-medium text-text-primary">{milestone.title}</p>
                        <p className="text-[13px] text-text-secondary">
                          Due: {milestone.dueDate || 'No date set'}
                        </p>
                      </div>
                      <div className="flex items-center gap-4">
                        <div className="text-right">
                          <p className="text-[13px] font-semibold text-text-primary">{milestone.progress}%</p>
                        </div>
                        <button 
                          onClick={() => {
                            setEditingMilestone(milestone);
                            setShowMilestoneForm(true);
                          }}
                          className="text-[13px] text-primary hover:underline"
                        >
                          Edit
                        </button>
                        <button
                          onClick={async () => {
                            if (!window.confirm('Delete this milestone?')) return;
                            try {
                              await deleteMilestone(milestone.id);
                            } catch (err) {
                              setError(err.message || 'Could not delete the milestone.');
                            }
                          }}
                          className="text-[13px] text-red-500 hover:underline"
                        >
                          Delete
                        </button>
                      </div>
                    </div>
                    <div className="fet-progress-bar mt-2" style={{ height: '6px' }}>
                      <div 
                        className="fet-progress-bar-fill"
                        style={{ width: `${milestone.progress}%` }}
                      ></div>
                    </div>
                  </div>
                ))}
              </div>
            ) : (
              <p className="text-center text-text-secondary py-8">No milestones for this project</p>
            )}
          </div>
        )}

        {/* Groups Tab */}
        {activeTab === 'groups' && (
          <div>
            {projectGroups.length > 0 ? (
              <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                {projectGroups.map(group => {
                  const members = projectMembers.filter((m) => m.groupId === group.id);
                  return (
                    <div key={group.id} className="p-4 bg-page-bg rounded-lg">
                      <h4 className="font-semibold text-text-primary">{group.name || 'Unnamed group'}</h4>
                      <p className="text-[13px] text-text-secondary">Lead: {group.leaderName || 'Not assigned'}</p>
                      <p className="text-[13px] text-text-secondary">Members: {members.length}</p>
                    </div>
                  );
                })}
              </div>
            ) : (
              <p className="text-center text-text-secondary py-8">No groups for this project</p>
            )}
          </div>
        )}
      </div>

      {/* Milestone Form Modal */}
      {showMilestoneForm && (
        <div className="fixed inset-0 bg-black/50 flex items-center justify-center z-50 p-4">
          <div className="bg-white rounded-xl shadow-xl max-w-md w-full">
            <div className="flex items-center justify-between p-6 border-b border-border-default">
              <h3 className="text-[15px] font-bold text-text-primary">
                {editingMilestone ? 'Edit Milestone' : 'Add Milestone'}
              </h3>
              <button 
                onClick={() => {
                  setShowMilestoneForm(false);
                  setEditingMilestone(null);
                }} 
                className="p-1 hover:bg-page-bg rounded-lg transition-colors"
              >
                <X size={24} className="text-text-secondary" />
              </button>
            </div>
            <form onSubmit={handleMilestoneSubmit} className="p-6 space-y-4">
              <div>
                <label className="fet-label">Title</label>
                <input
                  type="text"
                  name="title"
                  defaultValue={editingMilestone?.title || ''}
                  required
                  className="fet-input"
                />
              </div>
              <div>
                <label className="fet-label">Progress (%)</label>
                <input
                  type="number"
                  name="progress"
                  defaultValue={editingMilestone?.progress || 0}
                  min="0"
                  max="100"
                  className="fet-input"
                />
              </div>
              <div>
                <label className="fet-label">Due Date</label>
                <input
                  type="date"
                  name="dueDate"
                  defaultValue={editingMilestone?.dueDate || ''}
                  className="fet-input"
                />
              </div>
              <div className="flex justify-end gap-3 pt-4 border-t border-border-default">
                <button
                  type="button"
                  onClick={() => {
                    setShowMilestoneForm(false);
                    setEditingMilestone(null);
                  }}
                  className="fet-btn-secondary"
                >
                  Cancel
                </button>
                <button
                  type="submit"
                  className="fet-btn-primary"
                >
                  {editingMilestone ? 'Update' : 'Add'} Milestone
                </button>
              </div>
            </form>
          </div>
        </div>
      )}
    </div>
  );
};

export default ProjectDetails;
