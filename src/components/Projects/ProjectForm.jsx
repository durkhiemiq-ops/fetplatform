import React, { useState } from 'react';
import { STATUS_LABELS } from './projectUi';
import { Users, User, Layers, Info } from 'lucide-react';

export const SCOPE_OPTIONS = [
  {
    value: 'INDIVIDUAL',
    label: 'Individual',
    blurb: 'Every enrolled student submits their own work on this project.',
    icon: User,
  },
  {
    value: 'CLASS_WIDE',
    label: 'Class-wide (grouped)',
    blurb: 'One project for the whole class. The class forms groups and every group works on the same project together.',
    icon: Users,
  },
  {
    value: 'GROUP_SPECIFIC',
    label: 'Assigned to one group',
    blurb: 'An independent project for a single group, with its own tasks, deadline and marks.',
    icon: Layers,
  },
];

const toDateTimeLocal = (iso) => {
  if (!iso) return '';
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return '';
  const pad = (n) => String(n).padStart(2, '0');
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}T${pad(d.getHours())}:${pad(d.getMinutes())}`;
};

const ProjectForm = ({ project, courses = [], groupOptions = [], onOfferingChange, onClose, onSave, saving }) => {
  const [formData, setFormData] = useState({
    title: project?.title || '',
    course_offering: project?.course_offering || '',
    description: project?.description || '',
    objectives: project?.objectives || '',
    deadline: toDateTimeLocal(project?.deadline),
    status: project?.status || 'DRAFT',
    scope: project?.scope || 'INDIVIDUAL',
    group: project?.group || '',
  });

  const handleChange = (e) => {
    const { name, value } = e.target;
    setFormData((prev) => ({ ...prev, [name]: value }));
    // Groups are per-offering, so refresh them as soon as the course changes.
    if (name === 'course_offering' && onOfferingChange) onOfferingChange(value);
  };

  const handleSubmit = (e) => {
    e.preventDefault();
    const payload = {
      title: formData.title,
      description: formData.description,
      objectives: formData.objectives,
      deadline: formData.deadline ? new Date(formData.deadline).toISOString() : null,
    };
    if (project) {
      payload.status = formData.status;
      payload.scope = formData.scope;
      if (formData.scope === 'GROUP_SPECIFIC') payload.group = formData.group;
    } else {
      payload.course_offering = formData.course_offering;
      payload.scope = formData.scope;
      if (formData.scope === 'GROUP_SPECIFIC') payload.group = formData.group;
    }
    onSave(payload, project);
  };

  const activeScope = SCOPE_OPTIONS.find((s) => s.value === formData.scope) || SCOPE_OPTIONS[0];
  const ActiveIcon = activeScope.icon;
  // A group-assigned project needs a group to point at.
  const needsGroup = formData.scope === 'GROUP_SPECIFIC';
  const groupMissing = needsGroup && !formData.group;

  return (
    <form onSubmit={handleSubmit} className="space-y-4">
      <div>
        <label className="fet-label">Project Title</label>
        <input
          type="text"
          name="title"
          value={formData.title}
          onChange={handleChange}
          required
          className="fet-input"
        />
      </div>

      {!project && (
        <div>
          <label className="fet-label">Course Offering</label>
          <select
            name="course_offering"
            value={formData.course_offering}
            onChange={handleChange}
            required
            className="fet-select"
          >
            <option value="">Select a course you teach...</option>
            {courses.map((c) => (
              <option key={c.offering_id} value={c.offering_id}>
                {c.course_code} — {c.course_title} ({c.semester})
              </option>
            ))}
          </select>
          {courses.length === 0 && (
            <p className="text-[12px] text-red-500 mt-1">No active courses found for your account.</p>
          )}
        </div>
      )}

      <div>
        <label className="fet-label">How is the work divided?</label>
        <div className="space-y-2">
          {SCOPE_OPTIONS.map((opt) => {
            const Icon = opt.icon;
            const selected = formData.scope === opt.value;
            return (
              <label
                key={opt.value}
                className={`flex items-start gap-3 p-3 rounded-lg border cursor-pointer transition-colors ${
                  selected
                    ? 'border-primary bg-primary/5'
                    : 'border-border-default hover:border-primary/40'
                }`}
              >
                <input
                  type="radio"
                  name="scope"
                  value={opt.value}
                  checked={selected}
                  onChange={handleChange}
                  className="mt-1 h-4 w-4 accent-primary"
                />
                <span className="min-w-0">
                  <span className="flex items-center gap-2 text-sm font-medium text-text-primary">
                    <Icon size={14} />
                    {opt.label}
                  </span>
                  <span className="block text-[12px] text-text-secondary mt-0.5">{opt.blurb}</span>
                </span>
              </label>
            );
          })}
        </div>
      </div>

      {needsGroup && (
        <div>
          <label className="fet-label">Group</label>
          <select
            name="group"
            value={formData.group}
            onChange={handleChange}
            required
            className="fet-select"
          >
            <option value="">Select a group...</option>
            {groupOptions.map((g) => (
              <option key={g.id} value={g.id}>
                {g.name} — {g.project_title || 'Class project'}
              </option>
            ))}
          </select>
          {groupOptions.length === 0 ? (
            <p className="text-[12px] text-amber-600 mt-1 flex items-start gap-1">
              <Info size={13} className="mt-0.5 shrink-0" />
              No groups exist yet. Create a class-wide project first and let the class form groups,
              then come back to assign a project to a group.
            </p>
          ) : (
            <p className="text-[12px] text-text-secondary mt-1">
              Members of this group are copied into the new project automatically.
            </p>
          )}
        </div>
      )}

      {project && (
        <div>
          <label className="fet-label">Status</label>
          <select
            name="status"
            value={formData.status}
            onChange={handleChange}
            className="fet-select"
          >
            {Object.entries(STATUS_LABELS).map(([value, label]) => (
              <option key={value} value={value}>{label}</option>
            ))}
          </select>
        </div>
      )}

      <div className="flex items-start gap-2 p-3 rounded-lg bg-page-bg text-[12px] text-text-secondary">
        <ActiveIcon size={14} className="mt-0.5 shrink-0" />
        <span>{activeScope.blurb}</span>
      </div>

      <div>
        <label className="fet-label">Description</label>
        <textarea
          name="description"
          value={formData.description}
          onChange={handleChange}
          rows={3}
          className="fet-input resize-none"
          placeholder="Brief description of the project"
        />
      </div>

      <div>
        <label className="fet-label">Objectives</label>
        <textarea
          name="objectives"
          value={formData.objectives}
          onChange={handleChange}
          rows={3}
          className="fet-input resize-none"
          placeholder="Key objectives / deliverables, one per line"
        />
      </div>

      <div>
        <label className="fet-label">Deadline</label>
        <input
          type="datetime-local"
          name="deadline"
          value={formData.deadline}
          onChange={handleChange}
          className="fet-input"
        />
      </div>

      <div className="flex justify-end gap-3 pt-4 border-t border-border-default">
        <button type="button" onClick={onClose} className="fet-btn-secondary">
          Cancel
        </button>
        <button type="submit" className="fet-btn-primary" disabled={saving || groupMissing}>
          {saving ? 'Saving...' : project ? 'Update Project' : 'Create Project'}
        </button>
      </div>
    </form>
  );
};

export default ProjectForm;