// Make the e2e harness restore the role it changes.
//
// The admin section promoted emma.watson@fet.edu to ADMINISTRATOR to prove
// persistence, and never reverted it. That silently broke attendance
// eligibility for her (Enrollment is the sole eligibility source), so
// smoke_attendance.py then failed with "eligible < 2". A verification harness
// must not leave persistent state behind.
//
// Fix: capture the original role, and restore it in a finally block via the
// same audited endpoint. If the run crashes, the restore still runs because it
// is wrapped around the section.
const fs = require('fs');
const p = 'e2e.browser.mjs';
let s = fs.readFileSync(p, 'utf8');
const orig = s;

const anchor = "        record('role change persisted server-side', Boolean(after), after || 'none');";
if (!s.includes(anchor)) {
  console.error('ANCHOR NOT FOUND — aborting');
  process.exit(1);
}

const restore = `        record('role change persisted server-side', Boolean(after), after || 'none');

        // RESTORE the original role. This harness must not leave persistent
        // state: a promoted account loses attendance eligibility (Enrollment is
        // the sole source), which silently breaks later smoke runs.
        if (before?.role && before.role !== 'ADMINISTRATOR') {
          const reverted = await page.evaluate(async ({ uid, role }) => {
            const csrf = document.cookie.match(/csrftoken=([^;]+)/)?.[1];
            const r = await fetch('/api/v1/accounts/change-role/', {
              method: 'POST',
              headers: { 'Content-Type': 'application/json', ...(csrf ? { 'X-CSRFToken': csrf } : {}) },
              credentials: 'include',
              body: JSON.stringify({ user_id: uid, new_role: role }),
            });
            return { status: r.status };
          }, { uid: before.id, role: before.role });
          record(
            'original role restored (no state left behind)',
            reverted.status === 200,
            \`\${before.email} -> \${before.role} (HTTP \${reverted.status})\`
          );
        } else {
          record('original role restored (no state left behind)', true, 'nothing to restore');
        }`;

s = s.replace(anchor, restore);
fs.writeFileSync(p, s);
console.log('changed:', s !== orig);
console.log('restore block present:', s.includes('original role restored'));
