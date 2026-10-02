# FET Platform frontend

The repository has one React frontend in `frontend/` and one Django backend in
`backend/`. The client uses React 18, Vite, Tailwind, React Router, React Query,
and axios. The backend uses Django 6, Django REST Framework, PostgreSQL, and Redis.

## Integration status

The UI contains courses, attendance, learning materials, assessments, projects,
announcements, and administration screens. Backend alignment is in progress:
several screens call flat API routes that the current backend does not yet serve,
and some existing payloads differ. Screen availability does not establish that
the workflow is implemented or verified end to end. See
[the implementation plan](../docs/IMPLEMENTATION_PLAN.md) for the staged work.

The current signup flow also fabricates a local account and stores its password;
that frontend authentication defect remains scheduled for repair. Local browser
state must not establish identity, role, enrollment, or other domain authority.

## Local setup

Run shell commands with the required `rtk` prefix. From `frontend/`:

```powershell
rtk proxy npm install
rtk proxy npm run dev
```

Open [http://localhost:3000](http://localhost:3000). The shared axios client reads
`VITE_API_BASE` and defaults to `http://localhost:8000`; it appends `/api/v1`.
Set the backend origin, without `/api/v1`, in the ignored frontend `.env` if an
override is needed. Frontend environment variables are public client settings;
do not put secrets in them. Vite also proxies `/api` to `http://localhost:8000`,
although the default axios URL accesses the backend directly.

The backend requires system Python 3.14 on this machine; its virtual environment
interpreter is blocked by Application Control. With the ignored backend `.env`
configured and PostgreSQL/Redis available, run from `backend/`:

```powershell
rtk proxy python manage.py migrate
rtk proxy python manage.py runserver 127.0.0.1:8000
```

`manage.py` defaults to `config.settings`, the real PostgreSQL/Redis stack.
`config.settings_dev` is for isolated SQLite testing and local runs; it still
imports base settings and requires a secret key. Its cache uses Redis when
`USE_REDIS_CACHE` is enabled, otherwise local memory. Never print or commit `.env`
contents. Demo seeding is not part of the standard startup procedure.

## Authentication and API boundary

Authentication uses Django session cookies, not JWT. The shared client in
`src/lib/api.js` sends requests with credentials and obtains the CSRF cookie
through `/accounts/csrf/` before unsafe requests. It sends `X-CSRFToken` from that
cookie. `/auth/refresh/` checks session validity; it does not rotate a JWT.
Identity and permissions must come from the authenticated backend session.

Domain clients live in `src/lib/*.js`; `src/lib/auth.js` contains the authentication
requests. Keep snake_case on the wire and adapt any UI shape at that client
boundary. Use actual server responses instead of fabricated local successes.
The approved route target is flat `/api/v1/`; current backend prefixes still
need reconciliation. See `backend/config/urls.py` for routes that exist today.

## Source layout

```text
frontend/
  src/
    components/   Reusable UI components and feature screens
    Pages/        Page components
    lib/          Shared API client, domain clients, query and auth helpers
    context/      Existing React context
    App.jsx       Application routing
    main.jsx      Entry point
  index.html
  package.json
  vite.config.js
  tailwind.config.js
```

## Validation

From `frontend/`:

```powershell
rtk proxy npm run lint
rtk proxy npm run build
```

These checks validate source and bundling. Successful results do not establish
API compatibility or browser workflow correctness. Backend tests run from
`backend/` with `python manage.py test --settings=config.settings_dev`; PostgreSQL
concurrency and Redis atomicity require separate verification.

Internal use only - Faculty of Engineering and Technology.
