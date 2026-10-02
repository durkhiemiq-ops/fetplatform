/**
 * The shared vocabulary every screen is built from.
 *
 * One page anatomy, one set of spacing steps, one status language. If a screen
 * needs something that is not here, the right answer is usually to add it
 * here rather than to invent it locally.
 */
import React from 'react';
import { AlertCircle } from 'lucide-react';

/* ---------------------------------------------------------------- areas --- */

export const AREAS = {
  classrooms: { key: 'cls', label: 'Classrooms' },
  attendance: { key: 'att', label: 'Attendance' },
  projects: { key: 'prj', label: 'Projects' },
  announcements: { key: 'ann', label: 'Announcements' },
  hub: { key: 'hub', label: 'Workspace' },
};

/** A tinted square holding an icon. This is what makes an area recognisable. */
export function IconTile({ area = 'hub', icon: Icon, size = 'md' }) {
  const key = (AREA_MAP[area] || 'hub');
  const cls = `ui-tile${size === 'sm' ? ' ui-tile-sm' : size === 'lg' ? ' ui-tile-lg' : ''} a-${key}`;
  return (
    <span className={cls}>
      {Icon ? <Icon size={size === 'sm' ? 14 : size === 'lg' ? 18 : 17} /> : null}
    </span>
  );
}
const AREA_MAP = {
  classrooms: 'cls', classroom: 'cls',
  attendance: 'att',
  projects: 'prj', project: 'prj',
  announcements: 'ann', announcement: 'ann',
  hub: 'hub',
};

/* ----------------------------------------------------------------- text --- */

export function Eyebrow({ children, className = '' }) {
  return <span className={`ui-eyebrow ${className}`.trim()}>{children}</span>;
}

export function Crumb({ items = [] }) {
  return (
    <div className="ui-crumb">
      {items.map((item, i) => (
        <React.Fragment key={item.label}>
          {i > 0 && <Chevron />}
          {item.to
            ? <a href={item.to} className="hover:underline">{item.label}</a>
            : <b>{item.label}</b>}
        </React.Fragment>
      ))}
    </div>
  );
}
function Chevron() {
  return (
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"
         strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
      <polyline points="9 6 15 12 9 18" />
    </svg>
  );
}

/** The one page header. Title, one line of explanation, one primary action. */
export function SectionHeader({ area, icon, title, subtitle, actions, crumb }) {
  return (
    <>
      {crumb?.length ? <Crumb items={crumb} /> : null}
      <div className="ui-section-head">
        <div className="ui-section-title">
          <IconTile area={area} icon={icon} />
          <div>
            <h1 className="ui-h1">{title}</h1>
            {subtitle ? <p className="ui-sub">{subtitle}</p> : null}
          </div>
        </div>
        {actions ? <div className="flex items-center gap-2">{actions}</div> : null}
      </div>
    </>
  );
}

/* ---------------------------------------------------------------- cards --- */

export function Card({ accent, className = '', children, ...rest }) {
  const accentCls = accent ? ` ui-card-accent ac-${AREA_MAP[accent] || 'hub'}` : '';
  return (
    <div className={`ui-card${accentCls} ${className}`.trim()} {...rest}>
      {children}
    </div>
  );
}

export function CardHead({ title, square, children }) {
  return (
    <div className="ui-card-head">
      <div className="ui-card-title">
        {square ? (
          <span
            className="sq"
            style={{ background: square === true ? 'rgb(var(--line-2))' : `rgb(var(--area-${square}))` }}
          />
        ) : null}
        {title}
      </div>
      {children ? <div className="flex items-center gap-2">{children}</div> : null}
    </div>
  );
}

export function CardFoot({ children }) {
  return <div className="ui-card-foot">{children}</div>;
}

export function CardBody({ children, className = '' }) {
  return <div className={`ui-card-body ${className}`.trim()}>{children}</div>;
}

/* ---------------------------------------------------------------- stats --- */

export function StatTile({ area, icon, label, value, note, noteTone, children }) {
  return (
    <Card accent={area} className="h-full">
      <div className="ui-stat">
        {icon ? <IconTile area={area} icon={icon} size="lg" /> : null}
        <div className="min-w-0">
          <Eyebrow>{label}</Eyebrow>
          <div className="ui-stat-value">{value}</div>
          {note ? <div className={`ui-stat-note${noteTone ? ` ${noteTone}` : ''}`}>{note}</div> : null}
          {children}
        </div>
      </div>
    </Card>
  );
}

/* -------------------------------------------------------------- status --- */

export function Pill({ tone = 'mute', dot = false, icon: Icon, children }) {
  return (
    <span className={`ui-pill pill-${tone}`}>
      {dot ? <i /> : null}
      {Icon ? <Icon size={12} /> : null}
      {children}
    </span>
  );
}

export function Tag({ children }) {
  return <span className="ui-tag">{children}</span>;
}

/* ---------------------------------------------------------------- lists --- */

export function ListRow({ children, className = '' }) {
  return <div className={`ui-li ${className}`.trim()}>{children}</div>;
}

export function Avatar({ name = '', size = 34, tone = '#8A4661', title }) {
  const initials = name.split(' ').map((n) => n[0]).join('').toUpperCase().slice(0, 2) || '?';
  return (
    <span
      className="ui-avatar"
      title={title || name}
      style={{ width: size, height: size, fontSize: Math.round(size * 0.34), background: tone }}
    >
      {initials}
    </span>
  );
}

export function AvatarStack({ people = [], max = 4, size = 25, tones = [] }) {
  const shown = people.slice(0, max);
  const rest = people.length - shown.length;
  return (
    <div className="ui-stack">
      {shown.map((p, i) => (
        <span
          key={p.name || i}
          style={{
            width: size, height: size, fontSize: Math.round(size * 0.38),
            background: tones[i % tones.length] || '#4A5261',
          }}
          title={p.name}
        >
          {p.name.split(' ').map((n) => n[0]).join('').toUpperCase().slice(0, 2)}
        </span>
      ))}
      {rest > 0 ? (
        <span className="more" style={{ width: size, height: size, fontSize: Math.round(size * 0.38) }}>
          +{rest}
        </span>
      ) : null}
    </div>
  );
}

/* ------------------------------------------------------------- controls --- */

export function Tabs({ tabs, active, onChange }) {
  return (
    <div className="ui-tabs" role="tablist">
      {tabs.map((t) => (
        <button
          key={t.key}
          type="button"
          role="tab"
          aria-selected={active === t.key}
          className={`ui-tab${active === t.key ? ' active' : ''}`}
          onClick={() => onChange && onChange(t.key)}
        >
          {t.icon ? <t.icon size={15} /> : null}
          {t.label}
          {t.count !== undefined ? <span className="n">{t.count}</span> : null}
        </button>
      ))}
    </div>
  );
}

export function Bar({ value = 0, tone, className = '' }) {
  const pct = Math.max(0, Math.min(100, value));
  return (
    <div className={`ui-bar${tone ? ` ${tone}` : ''} ${className}`.trim()}>
      <i style={{ width: `${pct}%` }} />
    </div>
  );
}

export function Callout({ tone = 'in', icon: Icon = AlertCircle, children, className = '' }) {
  return (
    <div className={`ui-callout co-${tone} ${className}`.trim()}>
      <Icon size={16} />
      <div className="min-w-0">{children}</div>
    </div>
  );
}

export function EmptyState({ icon: Icon, title, subtitle, action }) {
  return (
    <div className="ui-empty">
      {Icon ? <div className="ui-empty-mark"><Icon size={22} /></div> : null}
      <p className="ui-empty-title">{title}</p>
      {subtitle ? <p className="ui-empty-sub">{subtitle}</p> : null}
      {action ? <div className="mt-4 flex justify-center">{action}</div> : null}
    </div>
  );
}

/* --------------------------------------------------------------- tables --- */

export function DataTable({ columns, rows, empty }) {
  if (!rows.length) return empty || null;
  return (
    <table className="fet-table">
      <thead>
        <tr>
          {columns.map((c) => (
            <th key={c.key} style={c.width ? { width: c.width } : undefined}>{c.label}</th>
          ))}
        </tr>
      </thead>
      <tbody>
        {rows.map((row, i) => (
          <tr key={row.id || i}>
            {columns.map((c) => (
              <td key={c.key} className={c.align === 'right' ? 'text-right' : undefined}>
                {c.render ? c.render(row, i) : row[c.key]}
              </td>
            ))}
          </tr>
        ))}
      </tbody>
    </table>
  );
}

/* ------------------------------------------------------------- classroom --- */

/** Eight colour pairs chosen by hashing the course code, so each course keeps
 *  its own banner, the way Google Classroom does it. */
export const COURSE_PALETTES = [
  ['#5B7FC4', '#2F4E8C'],
  ['#4E9A7B', '#2A6350'],
  ['#C08A3E', '#8A5A20'],
  ['#4E90B0', '#2C6076'],
  ['#B5645E', '#8A3B36'],
  ['#7A6BA8', '#4F4376'],
  ['#3F8F8A', '#256260'],
  ['#A8637E', '#77405A'],
];

export function courseGradient(code = '') {
  let h = 0;
  for (let i = 0; i < code.length; i += 1) h = (h * 31 + code.charCodeAt(i)) >>> 0;
  const [from, to] = COURSE_PALETTES[h % COURSE_PALETTES.length];
  return `linear-gradient(118deg, ${from}, ${to})`;
}

export function CourseBanner({ code, title, meta }) {
  return (
    <div className="ui-course-banner" style={{ backgroundImage: courseGradient(code) }}>
      <span className="ui-course-code">{code}</span>
      <div className="ui-course-title">{title}</div>
      {meta ? <div className="ui-course-meta">{meta}</div> : null}
    </div>
  );
}

export function CourseFigures({ items }) {
  return (
    <div className="ui-course-figs">
      {items.map((f) => (
        <div className="ui-course-fig" key={f.label}>
          <Eyebrow>{f.label}</Eyebrow>
          <b className="num">{f.value}</b>
        </div>
      ))}
    </div>
  );
}

/* ------------------------------------------------------------------ live --- */

export function LiveBanner({ children }) {
  return (
    <div className="ui-live">
      <div className="ui-live-top">{children}</div>
    </div>
  );
}
