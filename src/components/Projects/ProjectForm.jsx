import React, { useState } from 'react';

const STATUS_OPTIONS = [
  ['draft', 'Draft'],
  ['active', 'Active'],
  ['completed', 'Completed'],
  ['archived', 'Archived'],
];

const ProjectForm = ({ project, onClose, onSave, saving }) => {
  const [title, setTitle] = useState(project?.title || '');
  const [status, setStatus] = useState(project?.status || 'draft');

  const handleSubmit = (event) => {
    event.preventDefault();
    if (project) {
      onSave({ status }, project);
      return;
    }
    onSave({ title: title.trim() }, project);
  };

  return (
    <form onSubmit={handleSubmit} className="space-y-4">
      {project ? (
        <>
          <div>
            <p className="fet-label">Project</p>
            <p className="rounded-lg bg-page-bg p-3 text-sm font-medium text-text-primary">
              {project.title}
            </p>
          </div>
          <div>
            <label className="fet-label" htmlFor="project-status">Lifecycle status</label>
            <select
              id="project-status"
              value={status}
              onChange={(event) => setStatus(event.target.value)}
              className="fet-select"
            >
              {STATUS_OPTIONS.map(([value, label]) => (
                <option key={value} value={value}>{label}</option>
              ))}
            </select>
            <p className="mt-1 text-xs text-text-secondary">
              The server permits only the next lifecycle transition and makes completed or archived projects read-only.
            </p>
          </div>
        </>
      ) : (
        <div>
          <label className="fet-label" htmlFor="project-title">Project title</label>
          <input
            id="project-title"
            type="text"
            value={title}
            onChange={(event) => setTitle(event.target.value)}
            required
            maxLength={255}
            className="fet-input"
          />
          <p className="mt-1 text-xs text-text-secondary">
            New projects start in draft. Members, groups, tasks, milestones, and evidence are added after creation.
          </p>
        </div>
      )}

      <div className="flex justify-end gap-3 border-t border-border-default pt-4">
        <button type="button" onClick={onClose} className="fet-btn-secondary">
          Cancel
        </button>
        <button
          type="submit"
          className="fet-btn-primary"
          disabled={saving || (!project && !title.trim()) || (project && status === project.status)}
        >
          {saving ? 'Saving...' : project ? 'Change status' : 'Create project'}
        </button>
      </div>
    </form>
  );
};

export default ProjectForm;
