import React, { useState } from 'react';
import { useAppContext } from '../../context/AppContext';

/**
 * TaskForm — creates a task through the real contract.
 *
 * H5: `priority` and `dueDate` do not exist on ProjectTask, and `project` is a
 * UUID (the form previously sent a project TITLE). Status vocabulary is
 * todo | in_progress | completed.
 */
const TaskForm = ({ task, onClose, onSuccess }) => {
  const { addTask, updateTask, projects, students, capabilities } = useAppContext();
  const [formData, setFormData] = useState({
    title: task?.title || '',
    projectId: task?.project || projects[0]?.id || '',
    assignee: task?.assignee || '',
    status: task?.status || 'todo',
  });
  const [error, setError] = useState('');
  const [busy, setBusy] = useState(false);

  const handleSubmit = async (e) => {
    e.preventDefault();
    setError('');
    setBusy(true);
    try {
      if (task) {
        await updateTask(task.id, { status: formData.status });
      } else {
        if (!formData.projectId) {
          setError('Choose the project this task belongs to.');
          setBusy(false);
          return;
        }
        await addTask({
          title: formData.title,
          projectId: formData.projectId,
          assignee: formData.assignee || undefined,
          status: formData.status,
        });
      }
      onSuccess && onSuccess();
    } catch (err) {
      setError(err.message || 'Could not save the task.');
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
        <label className="fet-label">Task Title</label>
        <input
          type="text"
          name="title"
          value={formData.title}
          onChange={(e) => setFormData((prev) => ({ ...prev, title: e.target.value }))}
          required
          className="fet-input"
        />
      </div>

      {!task && (
        <>
          <div>
            <label className="fet-label">Project</label>
            <select
              name="projectId"
              value={formData.projectId}
              onChange={(e) => setFormData((prev) => ({ ...prev, projectId: e.target.value }))}
              className="fet-select"
              required
            >
              <option value="">Select a project…</option>
              {projects.map((p) => (
                <option key={p.id} value={p.id}>{p.title}</option>
              ))}
            </select>
          </div>

          {/* BR-111: an assignee must be an authorized project participant, so
              the picker is limited to known students. */}
          <div>
            <label className="fet-label">Assignee</label>
            <select
              name="assignee"
              value={formData.assignee}
              onChange={(e) => setFormData((prev) => ({ ...prev, assignee: e.target.value }))}
              className="fet-select"
            >
              <option value="">Unassigned</option>
              {students.map((s) => (
                <option key={s.id} value={s.id}>
                  {`${s.first_name || ''} ${s.last_name || ''}`.trim() || s.username}
                </option>
              ))}
            </select>
          </div>
        </>
      )}

      <div>
        <label className="fet-label">Status</label>
        <select
          name="status"
          value={formData.status}
          onChange={(e) => setFormData((prev) => ({ ...prev, status: e.target.value }))}
          className="fet-select"
        >
          <option value="todo">To do</option>
          <option value="in_progress">In Progress</option>
          <option value="completed">Completed</option>
        </select>
      </div>

      <div className="flex justify-end gap-3 pt-4 border-t border-border-default">
        <button type="button" onClick={onClose} className="fet-btn-secondary" disabled={busy}>
          Cancel
        </button>
        <button type="submit" className="fet-btn-primary disabled:opacity-60" disabled={busy}>
          {busy ? 'Saving…' : task ? 'Update Task' : 'Create Task'}
        </button>
      </div>
    </form>
  );
};

export default TaskForm;
