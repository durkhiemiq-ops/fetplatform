import React, { useState } from 'react';
import { useAppContext } from '../../context/AppContext';

/**
 * ProjectForm — creates/advances a project through the real contract.
 *
 * H5: ProjectCreateSerializer accepts `title` ONLY, and status changes go
 * through the lifecycle PATCH (draft → active → completed → archived; one step
 * forward at a time, BR-140..143). The previous form collected group,
 * supervisor, description, deadline and progress — none of which the model has —
 * and sent them all in a create that always ignored them.
 */
const ProjectForm = ({ project, onClose, onSuccess }) => {
  const { addProject, updateProject } = useAppContext();
  const [title, setTitle] = useState(project?.title || '');
  const [status, setStatus] = useState(project?.status || 'draft');
  const [error, setError] = useState('');
  const [busy, setBusy] = useState(false);

  // BR-142: the lifecycle only moves forward, one defined state at a time.
  const LIFECYCLE = ['draft', 'active', 'completed', 'archived'];
  const nextStatus = project ? LIFECYCLE[LIFECYCLE.indexOf(project.status) + 1] : null;

  const handleSubmit = async (e) => {
    e.preventDefault();
    setError('');
    setBusy(true);
    try {
      if (project) {
        await updateProject(project.id, { status });
      } else {
        await addProject({ title });
      }
      onSuccess && onSuccess();
    } catch (err) {
      setError(err.message || 'Could not save the project.');
    } finally {
      setBusy(false);
    }
  };

  return (
    <form onSubmit={handleSubmit} className="space-y-4">
      {error && (
        <div className="rounded-lg border border-red-200 bg-red-50 px-3 py-2 text-[13px] text-red-700">
          {error}
        </div>
      )}

      <div>
        <label className="fet-label">Project Title</label>
        <input
          type="text"
          name="title"
          value={title}
          onChange={(e) => setTitle(e.target.value)}
          required
          disabled={Boolean(project)}
          className="fet-input"
        />
        {project && (
          <p className="mt-1 text-[11px] text-text-secondary">
            The title cannot be changed after creation.
          </p>
        )}
      </div>

      {project && (
        <div>
          <label className="fet-label">Lifecycle status</label>
          <select
            name="status"
            value={status}
            onChange={(e) => setStatus(e.target.value)}
            className="fet-select"
          >
            <option value={project.status}>{project.status} (current)</option>
            {nextStatus && <option value={nextStatus}>Advance to {nextStatus}</option>}
          </select>
          <p className="mt-1 text-[11px] text-text-secondary">
            Projects move forward one step at a time: draft → active → completed → archived.
          </p>
        </div>
      )}

      <div className="flex justify-end gap-3 pt-4 border-t border-border-default">
        <button type="button" onClick={onClose} className="fet-btn-secondary" disabled={busy}>
          Cancel
        </button>
        <button type="submit" className="fet-btn-primary disabled:opacity-60" disabled={busy}>
          {busy ? 'Saving…' : project ? 'Update' : 'Create Project'}
        </button>
      </div>
    </form>
  );
};

export default ProjectForm;
