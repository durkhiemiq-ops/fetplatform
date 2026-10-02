import React, { useState } from 'react';
import { useAppContext } from '../../context/AppContext';
import { Plus, Search, CheckCircle, Clock, AlertCircle, X } from 'lucide-react';
import TaskForm from './TaskForm';
import { taskStatusLabel } from '../../utils/mappers';

const TaskList = () => {
  const { tasks, projects, updateTask, deleteTask } = useAppContext();
  const [searchTerm, setSearchTerm] = useState('');
  const [filter, setFilter] = useState('all');
  const [showForm, setShowForm] = useState(false);
  const [editingTask, setEditingTask] = useState(null);
  const [notice, setNotice] = useState('');
  const [error, setError] = useState('');

  const filteredTasks = tasks.filter(t => {
    const matchesSearch = t.title.toLowerCase().includes(searchTerm.toLowerCase());
    const matchesFilter = filter === 'all' || t.status === filter;
    return matchesSearch && matchesFilter;
  });

  // H5: backend statuses are todo | in_progress | completed.
  const getStatusIcon = (status) => {
    switch (status) {
      case 'completed': return <CheckCircle size={16} className="text-green-500" />;
      case 'in_progress': return <Clock size={16} className="text-yellow-500" />;
      default: return <AlertCircle size={16} className="text-gray-400" />;
    }
  };

  const getStatusColor = (status) => {
    switch (status) {
      case 'completed': return 'fet-badge fet-badge-completed';
      case 'in_progress': return 'fet-badge fet-badge-pending';
      default: return 'fet-badge fet-badge-inactive';
    }
  };

  const handleToggleStatus = async (task) => {
    setError('');
    const newStatus = task.status === 'completed' ? 'todo' : 'completed';
    try {
      await updateTask(task.id, { status: newStatus });
    } catch (err) {
      setError(err.message || 'Could not update the task.');
    }
  };

  const handleDelete = async (task) => {
    if (!window.confirm(`Delete task "${task.title}"?`)) return;
    setError('');
    try {
      await deleteTask(task.id);
    } catch (err) {
      setError(err.message || 'Could not delete the task.');
    }
  };

  return (
    <div className="space-y-6">
      <div className="flex flex-col sm:flex-row items-start sm:items-center justify-between gap-4">
        <div>
          <h2 className="text-[22px] font-bold text-text-primary">Tasks</h2>
          <p className="text-text-secondary">Manage your project tasks</p>
        </div>
        <button 
          onClick={() => setShowForm(true)}
          className="fet-btn-primary"
        >
          <Plus size={18} />
          Add Task
        </button>
      </div>

      {error && (
        <div className="rounded-lg border border-red-200 bg-red-50 px-4 py-2.5 text-[13px] text-red-700">
          {error}
        </div>
      )}

      <div className="flex flex-col sm:flex-row gap-4">
        <div className="relative flex-1">
          <Search className="absolute left-3 top-1/2 transform -translate-y-1/2 text-text-secondary" size={18} />
          <input
            type="text"
            placeholder="Search tasks..."
            value={searchTerm}
            onChange={(e) => setSearchTerm(e.target.value)}
            className="fet-input pl-10"
          />
        </div>
        <select
          value={filter}
          onChange={(e) => setFilter(e.target.value)}
          className="fet-select"
        >
          <option value="all">All Tasks</option>
          <option value="todo">To do</option>
          <option value="in_progress">In Progress</option>
          <option value="completed">Completed</option>
        </select>
      </div>

      <div className="fet-card overflow-hidden">
        <div className="overflow-x-auto">
          <table className="fet-table">
            <thead>
              <tr className="bg-page-bg border-b border-border-default">
                <th className="text-left py-3 px-4 text-[13px] font-semibold text-text-secondary uppercase">Task</th>
                <th className="text-left py-3 px-4 text-[13px] font-semibold text-text-secondary uppercase">Project</th>
                <th className="text-left py-3 px-4 text-[13px] font-semibold text-text-secondary uppercase">Assignee</th>
                <th className="text-left py-3 px-4 text-[13px] font-semibold text-text-secondary uppercase">Created</th>
                <th className="text-left py-3 px-4 text-[13px] font-semibold text-text-secondary uppercase">Status</th>
                <th className="text-left py-3 px-4 text-[13px] font-semibold text-text-secondary uppercase">Actions</th>
              </tr>
            </thead>
            <tbody>
              {filteredTasks.map((task) => {
                const project = projects.find((p) => p.id === task.project);
                return (
                <tr key={task.id} className="border-b border-border-default hover:bg-page-bg transition-colors">
                  <td className="py-3 px-4 font-medium text-text-primary">{task.title}</td>
                  <td className="py-3 px-4 text-text-secondary text-[13px]">{project?.title || '—'}</td>
                  <td className="py-3 px-4 text-text-secondary text-[13px]">{task.assigneeName || 'Unassigned'}</td>
                  <td className="py-3 px-4 text-text-secondary text-[13px]">
                    {task.created_at ? new Date(task.created_at).toLocaleDateString() : '—'}
                  </td>
                  <td className="py-3 px-4">
                    <span className={`${getStatusColor(task.status)} flex items-center gap-1 w-fit`}>
                      {getStatusIcon(task.status)}
                      {taskStatusLabel(task.status)}
                    </span>
                  </td>
                  <td className="py-3 px-4">
                    <div className="flex gap-2">
                      <button
                        onClick={() => handleToggleStatus(task)}
                        className="text-[13px] text-primary hover:underline"
                      >
                        {task.status === 'completed' ? 'Reopen' : 'Complete'}
                      </button>
                      <button
                        onClick={() => {
                          setEditingTask(task);
                          setShowForm(true);
                        }}
                        className="text-[13px] text-primary hover:underline"
                      >
                        Edit
                      </button>
                      <button
                        onClick={() => handleDelete(task)}
                        className="text-[13px] text-red-500 hover:underline"
                      >
                        Delete
                      </button>
                    </div>
                  </td>
                </tr>
                );
              })}
            </tbody>
          </table>
        </div>
        {filteredTasks.length === 0 && (
          <div className="text-center py-8 text-text-secondary">
            No tasks found. Create your first task!
          </div>
        )}
      </div>

      {showForm && (
        <div className="fixed inset-0 bg-black/50 flex items-center justify-center z-50 p-4">
          <div className="bg-white rounded-xl shadow-xl max-w-lg w-full">
            <div className="flex items-center justify-between p-6 border-b border-border-default">
              <h3 className="text-[15px] font-bold text-text-primary">
                {editingTask ? 'Edit Task' : 'Create New Task'}
              </h3>
              <button 
                onClick={() => {
                  setShowForm(false);
                  setEditingTask(null);
                }} 
                className="p-1 hover:bg-page-bg rounded-lg transition-colors"
              >
                <X size={24} className="text-text-secondary" />
              </button>
            </div>
            <div className="p-6">
              <TaskForm 
                task={editingTask}
                onClose={() => {
                  setShowForm(false);
                  setEditingTask(null);
                }}
                onSuccess={() => {
                  setShowForm(false);
                  setEditingTask(null);
                }}
              />
            </div>
          </div>
        </div>
      )}
    </div>
  );
};

export default TaskList;
