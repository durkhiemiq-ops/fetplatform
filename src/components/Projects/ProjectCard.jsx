import React from 'react';
import { useNavigate } from 'react-router-dom';
import { Users, Calendar, ArrowRight } from 'lucide-react';

const ProjectCard = ({ project }) => {
  const navigate = useNavigate();

  return (
    <div className="fet-card p-6 hover:shadow-md transition-shadow">
      <div className="flex items-start justify-between mb-3">
        <div>
          <h3 className="text-[15px] font-semibold text-text-primary">{project.title}</h3>
          <div className="flex items-center gap-3 text-[13px] text-text-secondary mt-1">
            <span className="flex items-center gap-1">
              <Users size={14} />
              {project.group || 'No group'}
            </span>
            <span>•</span>
            <span>{project.supervisorName || 'No supervisor'}</span>
          </div>
        </div>
        <span className={`fet-badge ${
          project.status === 'active'
            ? 'fet-badge-active'
            : project.status === 'archived'
            ? 'fet-badge-inactive'
            : 'fet-badge-warning'
        }`}>
          {project.status || 'draft'}
        </span>
      </div>

      {/* H5: Project has no description/progress/deadline columns. Render only
          fields the backend actually returns, rather than a progress bar that
          is permanently 0% and a deadline that is always blank. */}
      <div className="mb-4 flex items-center justify-between">
        <div className="flex items-center gap-2 text-[13px] text-text-secondary">
          <Calendar size={14} />
          <span>Created {project.created_at ? new Date(project.created_at).toLocaleDateString() : '—'}</span>
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
