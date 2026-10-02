import React from 'react';
import { useAppContext } from '../../context/AppContext';
import { Calendar, Info } from 'lucide-react';

/**
 * SchoolYearManager — read-only view of school years.
 *
 * H3/H4: the backend's SchoolYear model has NO is_active field and exposes no
 * PATCH/DELETE endpoint — only GET (and an admin-only POST). The previous
 * version offered Edit, Delete and "Switch current year" controls that either
 * did nothing at all or bound to a field that does not exist, so every date
 * rendered blank and "Switch" was permanently inert. Those controls are removed
 * rather than left looking functional. Dates now come from the central mapper
 * (start_date / end_date → startDate / endDate).
 */
const SchoolYearManager = () => {
  const { schoolYears, capabilities } = useAppContext();

  return (
    <div className="fet-card p-6">
      <div className="flex items-center justify-between mb-4">
        <h3 className="text-lg font-semibold text-text-primary flex items-center gap-2" style={{ fontSize: '15px' }}>
          <Calendar size={20} className="text-primary" />
          School Years
        </h3>
      </div>

      {capabilities?.admin && (
        <p className="mb-3 flex items-start gap-1.5 text-[11px] text-text-secondary">
          <Info size={12} className="mt-0.5 flex-shrink-0" />
          Creating and editing school years is not available: the API exposes reads only
          (no PATCH/DELETE, and no active-year flag on the model).
        </p>
      )}

      <div className="space-y-2">
        {schoolYears.length === 0 ? (
          <p className="text-sm text-text-secondary py-4 text-center">No school years available.</p>
        ) : (
          schoolYears.map((year) => (
            <div key={year.id} className="flex items-center justify-between p-3 rounded-xl bg-page-bg">
              <div>
                <p className="font-medium text-text-primary">{year.name}</p>
                <p className="text-xs text-text-secondary">
                  {year.startDate || '—'} – {year.endDate || '—'}
                </p>
              </div>
            </div>
          ))
        )}
      </div>
    </div>
  );
};

export default SchoolYearManager;
