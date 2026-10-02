import React, { useState } from 'react';
import { useAppContext } from '../../context/AppContext';
import { Plus, X, Bell, Calendar, AlertCircle, CheckCircle2, Info } from 'lucide-react';
import AnnouncementForm from './AnnouncementForm';

/**
 * AnnouncementList — renders the real AnnouncementSerializer shape.
 *
 * The backend sends {title, body, scope, scope_label, is_published,
 * is_important, published_at, created_by, created_at}. The previous version read
 * `type` / `date` / `author` / `content`, none of which exist server-side, so the
 * badge, date, author and body all rendered blank.
 */
const AnnouncementList = ({ user }) => {
  const { announcements, deleteAnnouncement, capabilities } = useAppContext();
  const [showForm, setShowForm] = useState(false);
  const [notice, setNotice] = useState('');

  // Only academic users may create announcements (BR-083).
  const canPost = capabilities?.academic;

  const typeMeta = (a) => {
    if (a.is_important) return { label: 'Important', cls: 'fet-badge-danger', Icon: AlertCircle };
    if (a.is_published) return { label: 'Announcement', cls: 'fet-badge-info', Icon: Info };
    return { label: 'Draft', cls: 'fet-badge-draft', Icon: Bell };
  };

  const handleDelete = async (a) => {
    if (!window.confirm('Delete this announcement?')) return;
    try {
      await deleteAnnouncement(a.id);
    } catch (err) {
      setNotice(err.message || 'Could not delete the announcement.');
      setTimeout(() => setNotice(''), 5000);
    }
  };

  return (
    <div className="space-y-6">
      {notice && (
        <div className="rounded-lg border border-amber-300 bg-amber-50 px-4 py-3 text-[13px] text-amber-900">
          {notice}
        </div>
      )}

      <div className="flex flex-col sm:flex-row items-start sm:items-center justify-between gap-4">
        <div>
          <h2 className="text-2xl font-bold text-text-primary">Announcements</h2>
          <p className="text-text-secondary" style={{ fontSize: '14px' }}>
            Stay updated with the latest news
          </p>
        </div>
        {canPost && (
          <button onClick={() => setShowForm(true)} className="fet-btn-primary flex items-center gap-2">
            <Plus size={18} />
            Post Announcement
          </button>
        )}
      </div>

      <div className="space-y-4">
        {announcements.length > 0 ? (
          announcements.map((a) => {
            const { label, cls, Icon } = typeMeta(a);
            return (
              <div key={a.id} className="fet-card p-6 hover:shadow-md transition-shadow">
                <div className="flex items-start justify-between">
                  <div className="flex-1">
                    <div className="flex items-center gap-3 mb-2 flex-wrap">
                      <span className={`fet-badge ${cls} inline-flex items-center gap-1`}>
                        <Icon size={12} /> {label}
                      </span>
                      {a.scopeLabel && (
                        <span className="text-xs text-text-secondary">Audience: {a.scopeLabel}</span>
                      )}
                      {a.date && (
                        <span className="text-xs text-text-secondary">
                          {new Date(a.date).toLocaleDateString()}
                        </span>
                      )}
                    </div>
                    <h3 className="text-lg font-semibold text-text-primary" style={{ fontSize: '15px' }}>
                      {a.title}
                    </h3>
                    <p className="text-text-secondary mt-2 whitespace-pre-line" style={{ fontSize: '14px' }}>
                      {a.content}
                    </p>
                  </div>
                  {canPost && (
                    <button
                      onClick={() => handleDelete(a)}
                      className="p-2 hover:bg-red-50 rounded-lg transition-colors"
                      aria-label="Delete announcement"
                    >
                      <X size={18} className="text-red-500" />
                    </button>
                  )}
                </div>
              </div>
            );
          })
        ) : (
          <div className="text-center py-12 fet-card">
            <Bell size={48} className="mx-auto text-text-secondary opacity-50" />
            <p className="text-text-secondary mt-4">No announcements yet.</p>
            {canPost && <p className="text-text-secondary text-[13px]">Post the first one above.</p>}
          </div>
        )}
      </div>

      {showForm && (
        <div className="fixed inset-0 bg-black/50 flex items-center justify-center z-50 p-4">
          <div className="bg-white rounded-xl shadow-xl max-w-lg w-full max-h-[95vh] overflow-y-auto">
            <div className="flex items-center justify-between p-6 border-b border-border-default">
              <h3 className="text-xl font-bold text-text-primary">Post Announcement</h3>
              <button onClick={() => setShowForm(false)} className="p-1 hover:bg-page-bg rounded-lg" aria-label="Close">
                <X size={22} className="text-text-secondary" />
              </button>
            </div>
            <div className="p-6">
              <AnnouncementForm
                onClose={() => setShowForm(false)}
                onSuccess={() => {
                  setShowForm(false);
                  setNotice('Announcement posted.');
                  setTimeout(() => setNotice(''), 4000);
                }}
              />
            </div>
          </div>
        </div>
      )}
    </div>
  );
};

export default AnnouncementList;
