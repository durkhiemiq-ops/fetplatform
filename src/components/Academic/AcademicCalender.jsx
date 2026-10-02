import React from 'react';
import { useAppContext } from '../../context/AppContext';
import SemesterSelector from './SemesterSelector';
import SchoolYearManager from './SchoolYearManager';

const AcademicCalendar = () => {
  const { currentSemester, currentSchoolYear } = useAppContext();

  return (
    <div className="space-y-6">
      <div className="fet-welcome-banner">
        <h2 className="text-2xl font-bold">Academic Calendar</h2>
        <p className="text-[#8683BA] mt-1">
          {currentSemester?.name} • {currentSchoolYear?.name}
        </p>
        <p className="text-[#8683BA] text-sm mt-1">
          {currentSemester?.startDate} - {currentSemester?.endDate}
        </p>
      </div>

      <SemesterSelector />
      <SchoolYearManager />

      {/* Semester Info */}
      <div className="fet-card p-6">
        <h3 className="text-lg font-semibold text-text-primary mb-4" style={{ fontSize: '15px' }}>Current Semester Information</h3>
        <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
          <div className="p-3 bg-page-bg rounded-xl text-center">
            <p className="text-xs text-text-secondary">Semester</p>
            <p className="font-semibold text-text-primary">{currentSemester?.name}</p>
          </div>
          <div className="p-3 bg-page-bg rounded-xl text-center">
            <p className="text-xs text-text-secondary">School Year</p>
            <p className="font-semibold text-text-primary">{currentSchoolYear?.name}</p>
          </div>
          <div className="p-3 bg-page-bg rounded-xl text-center">
            <p className="text-xs text-text-secondary">Start Date</p>
            <p className="font-semibold text-text-primary">{currentSemester?.startDate}</p>
          </div>
          <div className="p-3 bg-page-bg rounded-xl text-center">
            <p className="text-xs text-text-secondary">End Date</p>
            <p className="font-semibold text-text-primary">{currentSemester?.endDate}</p>
          </div>
        </div>
      </div>
    </div>
  );
};

export default AcademicCalendar;
