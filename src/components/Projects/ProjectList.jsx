import React, { useState } from 'react';
import { useAppContext } from '../../context/AppContext';
import { Plus, Filter, Search, X, Edit2, Trash2, FolderKanban } from 'lucide-react';
import ProjectCard from './ProjectCard';
import ProjectForm from './ProjectForm';

const ProjectsList = () => {
  const { projects, deleteProject } = useAppContext();
  const [searchTerm, setSearchTerm] = useState('');
  const [showForm, setShowForm] = useState(false);
  const [editingProject, setEditingProject] = useState(null);
  const [filter, setFilter] = useState('all');

  const filteredProjects = projects.filter(p => {
    const matchesSearch = p.title.toLowerCase().includes(searchTerm.toLowerCase()) ||
                          p.supervisor.toLowerCase().includes(searchTerm.toLowerCase());
    const matchesFilter = filter === 'all' || p.status === filter;
    return matchesSearch && matchesFilter;
  });

  const handleEdit = (project) => {
    setEditingProject(project);
    setShowForm(true);
  };

  const handleDelete = (id) => {
    if (window.confirm('Are you sure you want to delete this project?')) {
      deleteProject(id);
    }
  };

  const handleCloseForm = () => {
    setShowForm(false);
    setEditingProject(null);
  };

  return (
    <div className="space-y-6">
      <div className="flex flex-col sm:flex-row items-start sm:items-center justify-between gap-4">
        <div>
          <h2 className="text-[22px] font-bold text-text-primary">My Projects</h2>
          <p className="text-text-secondary text-[13px]">Manage and track your project progress</p>
        </div>
        <button 
          onClick={() => setShowForm(true)}
          className="fet-btn-primary"
        >
          <Plus size={16} />
          New Project
        </button>
      </div>

      <div className="flex flex-col sm:flex-row gap-4">
        <div className="relative flex-1">
          <Search className="absolute left-3 top-1/2 transform -translate-y-1/2 text-text-secondary" size={16} />
          <input
            type="text"
            placeholder="Search projects..."
            value={searchTerm}
            onChange={(e) => setSearchTerm(e.target.value)}
            className="fet-input pl-9"
          />
        </div>
        <select 
          value={filter}
          onChange={(e) => setFilter(e.target.value)}
          className="fet-select"
        >
          <option value="all">All Projects</option>
          <option value="Active">Active</option>
          <option value="Completed">Completed</option>
          <option value="On Hold">On Hold</option>
        </select>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        {filteredProjects.map((project) => (
          <div key={project.id} className="relative group">
            <ProjectCard project={project} />
            <div className="absolute top-4 right-4 flex gap-2 opacity-0 group-hover:opacity-100 transition-opacity">
              <button
                onClick={() => handleEdit(project)}
                className="p-1.5 bg-white rounded-lg shadow-md hover:bg-page-bg transition-colors"
                title="Edit Project"
              >
                <Edit2 size={15} className="text-primary" />
              </button>
              <button
                onClick={() => handleDelete(project.id)}
                className="p-1.5 bg-white rounded-lg shadow-md hover:bg-red-50 transition-colors"
                title="Delete Project"
              >
                <Trash2 size={15} className="text-red-500" />
              </button>
            </div>
          </div>
        ))}
      </div>

      {filteredProjects.length === 0 && (
        <div className="text-center py-12 fet-card">
          <FolderKanban size={48} className="mx-auto text-text-secondary opacity-50" />
          <p className="text-text-secondary mt-4 text-[13px]">No projects found. Create your first project!</p>
        </div>
      )}

      {showForm && (
        <div className="fixed inset-0 bg-black/50 flex items-center justify-center z-50 p-4">
          <div className="bg-white rounded-xl shadow-xl max-w-2xl w-full max-h-[90vh] overflow-y-auto">
            <div className="flex items-center justify-between p-6 border-b border-border-default">
              <h3 className="text-[15px] font-bold text-text-primary">
                {editingProject ? 'Edit Project' : 'Create New Project'}
              </h3>
              <button onClick={handleCloseForm} className="p-1 hover:bg-page-bg rounded-lg transition-colors">
                <X size={20} className="text-text-secondary" />
              </button>
            </div>
            <div className="p-6">
              <ProjectForm 
                project={editingProject} 
                onClose={handleCloseForm}
                onSuccess={() => {
                  handleCloseForm();
                }}
              />
            </div>
          </div>
        </div>
      )}
    </div>
  );
};

export default ProjectsList;
