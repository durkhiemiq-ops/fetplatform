import React, { useState } from 'react';
import { useAppContext } from '../../context/AppContext';
import { Plus, X, Users, Trash2, Edit2 } from 'lucide-react';
import GroupForm from './GroupForm';

const GroupList = () => {
  const { groups, deleteGroup } = useAppContext();
  const [showForm, setShowForm] = useState(false);
  const [editingGroup, setEditingGroup] = useState(null);

  return (
    <div className="space-y-6">
      <div className="flex flex-col sm:flex-row items-start sm:items-center justify-between gap-4">
        <div>
          <h2 className="text-[22px] font-bold text-text-primary">Groups</h2>
          <p className="text-text-secondary">Manage project groups</p>
        </div>
        <button 
          onClick={() => setShowForm(true)}
          className="fet-btn-primary"
        >
          <Plus size={18} />
          Create Group
        </button>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
        {groups.map((group) => (
          <div key={group.id} className="fet-card p-6 hover:shadow-md transition-shadow">
            <div className="flex items-start justify-between">
              <div className="flex-1">
                <div className="flex items-center gap-3 mb-2">
                  <div className="p-2 bg-primary/10 rounded-lg">
                    <Users size={20} className="text-primary" />
                  </div>
                  <h3 className="text-[15px] font-semibold text-text-primary">{group.name}</h3>
                </div>
                <p className="text-[13px] text-text-secondary">Project: {group.project}</p>
                <p className="text-[13px] text-text-secondary">Lead: {group.lead}</p>
                <p className="text-[13px] text-text-secondary">Members: {group.members}</p>
              </div>
              <div className="flex gap-2">
                <button
                  onClick={() => {
                    setEditingGroup(group);
                    setShowForm(true);
                  }}
                  className="p-1.5 hover:bg-page-bg rounded-lg transition-colors"
                >
                  <Edit2 size={16} className="text-primary" />
                </button>
                <button
                  onClick={() => {
                    if (window.confirm('Delete this group?')) {
                      deleteGroup(group.id);
                    }
                  }}
                  className="p-1.5 hover:bg-red-50 rounded-lg transition-colors"
                >
                  <Trash2 size={16} className="text-red-500" />
                </button>
              </div>
            </div>
          </div>
        ))}
      </div>

      {groups.length === 0 && (
        <div className="text-center py-12 fet-card">
          <Users size={48} className="mx-auto text-text-secondary opacity-50" />
          <p className="text-text-secondary mt-4">No groups yet. Create your first group!</p>
        </div>
      )}

      {showForm && (
        <div className="fixed inset-0 bg-black/50 flex items-center justify-center z-50 p-4">
          <div className="bg-white rounded-xl shadow-xl max-w-lg w-full">
            <div className="flex items-center justify-between p-6 border-b border-border-default">
              <h3 className="text-[15px] font-bold text-text-primary">
                {editingGroup ? 'Edit Group' : 'Create New Group'}
              </h3>
              <button 
                onClick={() => {
                  setShowForm(false);
                  setEditingGroup(null);
                }} 
                className="p-1 hover:bg-page-bg rounded-lg transition-colors"
              >
                <X size={24} className="text-text-secondary" />
              </button>
            </div>
            <div className="p-6">
              <GroupForm 
                group={editingGroup}
                onClose={() => {
                  setShowForm(false);
                  setEditingGroup(null);
                }}
                onSuccess={() => {
                  setShowForm(false);
                  setEditingGroup(null);
                }}
              />
            </div>
          </div>
        </div>
      )}
    </div>
  );
};

export default GroupList;
