# FET Platform - Faculty of Engineering and Technology

Academic Learning and Project Management System built with Vite + React (frontend) and Django REST Framework (backend).

## 🚀 Features

### Core Features
- ✅ **Dashboard** - Role-specific dashboards for Students, Lecturers, Coordinators, Admins
- ✅ **Course Management** - Course catalogue, enrollment, timetables
- ✅ **Lesson Materials** - Upload, download, and manage course learning materials
- ✅ **Project Management** - Create, read, update, delete projects with groups, tasks, milestones
- ✅ **Task Management** - Create, update, delete tasks with status tracking
- ✅ **Group Management** - Create, update, delete groups
- ✅ **Attendance Tracking** - QR-based attendance with projector/station modes (UI ready, backend integration in progress)
- ✅ **Assessment System** - Rubric-based continuous assessment
- ✅ **Contribution Tracking** - Monitor student contributions
- ✅ **Announcements** - Post and manage announcements with scope (faculty, department, course)
- ✅ **Milestones** - Track project milestones
- ✅ **Admin Panel** - User management, system statistics

### Technical Features
- ✅ **API Integration** - Connects to Django REST backend via JWT authentication (httpOnly cookies)
- ✅ **React Query** - Server state management with caching and background updates
- ✅ **Responsive Design** - Works on all screen sizes with mobile-friendly sidebar
- ✅ **Dark/Light Mode** - Using the FET design system
- ✅ **Search & Filter** - Find what you need quickly
- ✅ **Modal Forms** - Clean, intuitive CRUD operations

## 📦 Installation

### Prerequisites
- Node.js (v18 or higher)
- npm (v9 or higher)
- Python 3.11+ (for backend)
- PostgreSQL (or SQLite for development)

### Backend Setup
```bash
cd ../backend
python -m venv .venv
.venv\Scripts\activate        # Windows
pip install -r requirements.txt
python manage.py migrate
python manage.py seed_demo
python manage.py runserver
```

### Frontend Setup
```bash
cd FET-official
npm install
npm run dev
```

Open [http://localhost:3000](http://localhost:3000).

## 🔐 Demo Credentials (after seeding backend)

| Role    | Email                      | Password    |
|---------|----------------------------|-------------|
| Admin   | admin@fet.edu              | admin123    |
| Lecturer| dr.smith@fet.edu           | lecturer123 |
| Student | john.doe@student.fet.edu   | student123  |

## 🏗️ Architecture

- **Frontend**: Vite + React 18, React Router, React Query, Axios, Lucide Icons, Tailwind CSS
- **Backend**: Django 4.2, Django REST Framework, SimpleJWT, PostgreSQL
- **Authentication**: JWT in httpOnly cookies with automatic refresh
- **State Management**: React Query for server state, React Context for UI state

## 📁 Project Structure

```
FET-official/
├── public/
├── src/
│   ├── components/        # Reusable UI components
│   │   ├── Auth/          # Login, SignUp
│   │   ├── Layout/        # Sidebar, Header
│   │   ├── Dashboard/     # Role-specific dashboards
│   │   ├── Attendance/    # Attendance management
│   │   ├── Projects/      # Project, Task, Group components
│   │   ├── Assessment/    # Assessment and contributions
│   │   ├── Announcements/ # Announcement list/form
│   │   ├── Academic/      # Academic calendar, semester selector
│   │   └── ...
│   ├── Pages/             # Page-level components
│   │   ├── Courses/       # Course catalogue
│   │   ├── Lessons/       # Lesson materials (new)
│   │   └── Admin/         # Admin pages
│   ├── lib/               # API client, React Query provider, auth helpers
│   ├── context/           # React Context for global UI state
│   ├── data/              # Mock data (legacy, being phased out)
│   ├── App.jsx            # Main app with routing
│   └── main.jsx           # Entry point with QueryProvider
├── index.html
├── package.json
├── vite.config.js
└── tailwind.config.js
```

## 🔧 Development

```bash
# Start frontend only (requires backend running on port 8000)
npm run dev

# Build for production
npm run build

# Lint
npm run lint
```

## 🐳 Docker (Coming Soon)

```bash
docker-compose up --build
```

## 📝 License

Internal use only - Faculty of Engineering and Technology.