import React, { useCallback, useEffect, useState } from 'react';
import {
  ShieldCheck, RefreshCw, Search, AlertTriangle, Activity,
  UserCheck, KeyRound, ChevronLeft, ChevronRight,
} from 'lucide-react';
import { SectionHeader, Card, CardBody, CardHead, Pill } from '../UI';
import { auditApi, actionLabel, SENSITIVE_ACTIONS } from '../../lib/audit';
import { errorMessage } from '../../lib/enrollment';

const PAGE_SIZE = 20;

const StatTile = ({ icon: Icon, label, value, tone = 'default' }) => (
  <div className="rounded-xl border border-default bg-surface p-4">
    <div className="flex items-center gap-2 text-text-secondary text-[12px] font-medium">
      <Icon size={14} />
      <span className="uppercase tracking-wide">{label}</span>
    </div>
    <div className={`mt-2 text-2xl font-bold ${tone === 'alert' ? 'text-danger' : 'text-text-primary'}`}>
      {value}
    </div>
  </div>
);

const AuditLogConsole = () => {
  const [summary, setSummary] = useState(null);
  const [rows, setRows] = useState([]);
  const [actions, setActions] = useState([]);
  const [pagination, setPagination] = useState({ page: 1, total_pages: 1, total: 0 });
  const [action, setAction] = useState('');
  const [search, setSearch] = useState('');
  const [page, setPage] = useState(1);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');

  const loadSummary = useCallback(async () => {
    try {
      setSummary(await auditApi.summary());
    } catch {
      /* the header stats are not worth an error banner on their own */
    }
  }, []);

  const load = useCallback(async () => {
    setBusy(true);
    setError('');
    try {
      const data = await auditApi.list({ action, search, page, pageSize: PAGE_SIZE });
      setRows(data?.results ?? []);
      setActions(data?.available_actions ?? []);
      if (data?.pagination) setPagination(data.pagination);
    } catch (e) {
      setError(errorMessage(e));
    } finally {
      setBusy(false);
    }
  }, [action, search, page]);

  useEffect(() => { loadSummary(); }, [loadSummary]);
  useEffect(() => { load(); }, [load]);

  const applyFilter = (setter) => (value) => { setter(value); setPage(1); };

  return (
    <div className="space-y-5">
      <SectionHeader
        area="hub"
        icon={ShieldCheck}
        title="Security & Audit Log"
        subtitle="Every sensitive action the platform records, newest first. Read-only by design (BR-211)."
        actions={
          <button
            onClick={() => { load(); loadSummary(); }}
            disabled={busy}
            className="inline-flex items-center gap-2 rounded-lg border border-default px-3 py-1.5 text-[13px] font-medium hover:bg-page-bg disabled:opacity-50"
          >
            <RefreshCw size={14} className={busy ? 'animate-spin' : ''} />
            Refresh
          </button>
        }
      />

      {summary && (
        <div className="grid grid-cols-2 lg:grid-cols-4 gap-3">
          <StatTile icon={Activity} label="Events (24h)" value={summary.events_24h} />
          <StatTile
            icon={AlertTriangle}
            label="Failed sign-ins"
            value={summary.failed_logins_24h}
            tone={summary.failed_logins_24h > 0 ? 'alert' : 'default'}
          />
          <StatTile icon={UserCheck} label="Active actors" value={summary.distinct_actors_24h} />
          <StatTile icon={KeyRound} label="All-time events" value={summary.total_events} />
        </div>
      )}

      <Card>
        <CardHead>
          <div className="flex flex-wrap items-center gap-2">
            <select
              value={action}
              onChange={(e) => applyFilter(setAction)(e.target.value)}
              className="rounded-lg border border-default bg-surface px-2.5 py-1.5 text-[13px]"
            >
              <option value="">All actions</option>
              {actions.map((a) => (
                <option key={a} value={a}>{actionLabel(a)}</option>
              ))}
            </select>
            <div className="relative">
              <Search size={14} className="absolute left-2.5 top-1/2 -translate-y-1/2 text-text-secondary" />
              <input
                value={search}
                onChange={(e) => applyFilter(setSearch)(e.target.value)}
                placeholder="Filter actions…"
                className="rounded-lg border border-default bg-surface pl-8 pr-3 py-1.5 text-[13px]"
              />
            </div>
          </div>
        </CardHead>
        <CardBody className="p-0">
          {error && (
            <div className="m-4 rounded-lg border border-danger/40 bg-danger/5 px-3 py-2 text-[13px] text-danger">
              {error}
            </div>
          )}

          <div className="overflow-x-auto">
            <table className="w-full text-left text-[13px]">
              <thead className="border-b border-default text-[11px] uppercase tracking-wide text-text-secondary">
                <tr>
                  <th className="px-4 py-2.5 font-semibold">When</th>
                  <th className="px-4 py-2.5 font-semibold">Actor</th>
                  <th className="px-4 py-2.5 font-semibold">Action</th>
                  <th className="px-4 py-2.5 font-semibold">Resource</th>
                  <th className="px-4 py-2.5 font-semibold">Origin</th>
                </tr>
              </thead>
              <tbody>
                {rows.length === 0 && !busy && (
                  <tr>
                    <td colSpan={5} className="px-4 py-8 text-center text-text-secondary">
                      No audit events match this filter.
                    </td>
                  </tr>
                )}
                {rows.map((r) => (
                  <tr key={r.id} className="border-b border-default last:border-0">
                    <td className="px-4 py-2.5 whitespace-nowrap text-text-secondary">
                      {new Date(r.created_at).toLocaleString()}
                    </td>
                    <td className="px-4 py-2.5">
                      {r.actor_full_name || r.actor_email || (
                        <span className="text-text-secondary">system</span>
                      )}
                    </td>
                    <td className="px-4 py-2.5">
                      <Pill tone={SENSITIVE_ACTIONS.has(r.action) ? 'bd' : 'mu'}>
                        {actionLabel(r.action)}
                      </Pill>
                    </td>
                    <td className="px-4 py-2.5 text-text-secondary">{r.resource_type || '—'}</td>
                    <td className="px-4 py-2.5 text-text-secondary font-mono text-[12px]">
                      {r.ip_address || '—'}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>

          <div className="flex items-center justify-between px-4 py-3 border-t border-default text-[12px] text-text-secondary">
            <span>{pagination.total} event{pagination.total === 1 ? '' : 's'}</span>
            <div className="flex items-center gap-2">
              <button
                onClick={() => setPage((p) => Math.max(1, p - 1))}
                disabled={page <= 1 || busy}
                className="inline-flex items-center gap-1 rounded-lg border border-default px-2.5 py-1 disabled:opacity-40"
              >
                <ChevronLeft size={14} /> Prev
              </button>
              <span>Page {page} of {Math.max(1, pagination.total_pages)}</span>
              <button
                onClick={() => setPage((p) => p + 1)}
                disabled={page >= pagination.total_pages || busy}
                className="inline-flex items-center gap-1 rounded-lg border border-default px-2.5 py-1 disabled:opacity-40"
              >
                Next <ChevronRight size={14} />
              </button>
            </div>
          </div>
        </CardBody>
      </Card>
    </div>
  );
};

export default AuditLogConsole;
