import React from 'react';
import { useNavigate } from 'react-router-dom';
import { Users, Calendar, ArrowRight, CheckSquare, Layers } from 'lucide-react';
import { statusBadge } from './projectUi';

const ProjectCard = ({ project }) => {
  const navigate = useNavigate();
  const total = project.task_count || 0;
  const done = project.completed_task_count || 0;
  const progress = total > 0 ? Math.round((done / total) * 100) : 0;

  return (
    <div className="fet-card p-6 hover:shadow-md transition-shadow">
      <div className="flex items-start justify-between mb-3">
        <div className="min-w-0">
          <h3 className="text-[15px] font-semibold text-text-primary">{project.title}</h3>
          <div className="flex items-center gap-3 text-[13px] text-text-secondary mt-1 flex-wrap">
            <span className="flex items-center gap-1">
              <Layers size={14} />
              {project.course_code || '—'}
            </span>
            <span>•</span>
            <span>{project.supervisor_name || 'No supervisor'}</span>
          </div>
        </div>
        {statusBadge(project.status)}
      </div>

      <p className="text-[13px] text-text-secondary mb-4 line-clamp-2">
        {project.description || 'No description provided'}
      </p>

      <div className="mb-4">
        <div className="flex items-center justify-between text-[13px] text-text-secondary mb-1">
          <span>Task Completion</span>
          <span className="font-semibold text-text-primary">{progress}%</span>
        </div>
        <div className="fet-progress-bar">
          <div className="fet-progress-bar-fill" style={{ width: `${progress}%` }}></div>
        </div>
      </div>

      <div className="flex items-center justify-between">
        <div className="flex items-center gap-3 text-[13px] text-text-secondary">
          <span className="flex items-center gap-1">
            <Users size={14} />
            {project.member_count || 0}
          </span>
          <span className="flex items-center gap-1">
            <CheckSquare size={14} />
            {done}/{total} tasks
          </span>
          <span className="flex items-center gap-1">
            <Calendar size={14} />
            {project.deadline ? new Date(project.deadline).toLocaleDateString() : 'No deadline'}
          </span>
        </div>
        <button
          onClick={() => navigate(`/projects/${project.id}`)}
          className="flex items-center gap-1 text-primary hover:underline text-[13px] font-medium"
        >
          View Details
          <ArrowRight size={14} />
        </button>
      </div>
    </div>
  );
};

export default ProjectCard;