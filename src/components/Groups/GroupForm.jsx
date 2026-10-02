import React, { useState } from 'react';
import { useAppContext } from '../../context/AppContext';

const GroupForm = ({ group, onClose, onSuccess }) => {
  const { addGroup, updateGroup, projects } = useAppContext();
  const [formData, setFormData] = useState({
    name: group?.name || '',
    project: group?.project || projects[0]?.title || '',
    lead: group?.lead || '',
    members: group?.members || 0,
  });

  const handleSubmit = (e) => {
    e.preventDefault();
    if (group) {
      updateGroup(group.id, formData);
    } else {
      addGroup(formData);
    }
    onSuccess();
  };

  return (
    <form onSubmit={handleSubmit} className="space-y-4">
      <div>
        <label className="fet-label">Group Name</label>
        <input
          type="text"
          value={formData.name}
          onChange={(e) => setFormData(prev => ({ ...prev, name: e.target.value }))}
          required
          className="fet-input"
        />
      </div>

      <div>
        <label className="fet-label">Project</label>
        <select
          value={formData.project}
          onChange={(e) => setFormData(prev => ({ ...prev, project: e.target.value }))}
          className="fet-select"
        >
          {projects.map(p => (
            <option key={p.id} value={p.title}>{p.title}</option>
          ))}
        </select>
      </div>

      <div>
        <label className="fet-label">Group Lead</label>
        <input
          type="text"
          value={formData.lead}
          onChange={(e) => setFormData(prev => ({ ...prev, lead: e.target.value }))}
          className="fet-input"
        />
      </div>

      <div>
        <label className="fet-label">Number of Members</label>
        <input
          type="number"
          value={formData.members}
          onChange={(e) => setFormData(prev => ({ ...prev, members: parseInt(e.target.value) || 0 }))}
          min="0"
          className="fet-input"
        />
      </div>

      <div className="flex justify-end gap-3 pt-4 border-t border-border-default">
        <button
          type="button"
          onClick={onClose}
          className="fet-btn-secondary"
        >
          Cancel
        </button>
        <button
          type="submit"
          className="fet-btn-primary"
        >
          {group ? 'Update Group' : 'Create Group'}
        </button>
      </div>
    </form>
  );
};

export default GroupForm;
