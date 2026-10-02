"""Development demo seed: ``manage.py seed_demo``.

Idempotent (keyed on natural keys) so it is safe to re-run. Creates every row
the frontend needs to be meaningfully alive on first login:

- Faculty + Departments + Courses (codes match the frontend catalogue)
- One SUPERUSER admin, one LECTURER, two STUDENTs — all with
  ``is_email_verified=True`` (bypassing the OTP gate deliberately in seed data;
  BR-209 is a product-environment gate, not a demo impediment)
- SchoolYear + current Semester
- ClassSession (the anchor for all attendance)
- Enrollment rows linking students to courses
- One demo Project with tasks, a group, and a milestone
- One Announcement and one Notification

**Never run against production settings.**

Passwords are printed at the end and are deterministic for the demo.
"""

from __future__ import annotations

from django.core.management.base import BaseCommand, CommandError
from django.utils import timezone

from apps.academic.models import (
    ClassSession,
    Course,
    Department,
    Enrollment,
    Faculty,
    SchoolYear,
    Semester,
)
from apps.accounts.models import User
from apps.announcements.models import Announcement
from apps.notifications.services.notification_service import notify_role_changed
from apps.projects.models import (
    Project,
    ProjectGroup,
    ProjectGroupMembership,
    ProjectMilestone,
    ProjectTask,
)

import datetime as dt


class Command(BaseCommand):
    help = "Seed development demo data (idempotent; keyed on natural keys)."

    def handle(self, *args, **options):
        from django.conf import settings

        if not settings.DEBUG:
            raise CommandError(
                "seed_demo refuses to run with DEBUG=False. "
                "Use it only with config.settings_dev."
            )

        created = {}

        # ---- Academic structure ----
        faculty, _ = Faculty.objects.get_or_create(name="Faculty of Engineering and Technology")

        dept_specs = [
            ("Computer Engineering", "CE"),
            ("Civil Engineering", "CVE"),
            ("Chemical & Petroleum Engineering", "CHE"),
            ("Electrical & Electronic Engineering", "EE"),
            ("Mechanical & Industrial Engineering", "ME"),
        ]
        departments = {}
        for name, _code in dept_specs:
            dept, _ = Department.objects.get_or_create(name=name, defaults={"faculty": faculty})
            departments[name] = dept
        created["departments"] = len(departments)

        # ---- Users ----
        admin, _ = User.objects.get_or_create(
            email="admin@fet.local",
            defaults={
                "username": "admin",
                "first_name": "Admin",
                "last_name": "User",
            },
        )
        # Seeds are idempotent AND authoritative for demo identities: even if
        # the account already exists, the demo password and role come back.
        admin.username = "admin"
        admin.role = User.Role.ADMINISTRATOR
        admin.is_staff = True
        admin.is_superuser = True
        admin.is_email_verified = True  # seeds bypass the OTP gate by design
        admin.set_password("admin123")
        admin.save()

        lecturer, _ = User.objects.get_or_create(
            email="alida.vance@fet.edu",
            defaults={"username": "alida.vance"},
        )
        lecturer.first_name = "Alida"
        lecturer.last_name = "Vance"
        lecturer.role = User.Role.LECTURER
        lecturer.staffid = "LEC001"
        lecturer.is_email_verified = True
        lecturer.department = departments["Computer Engineering"]
        lecturer.set_password("lecturer123")
        lecturer.save()

        student_a, _ = User.objects.get_or_create(
            email="alex.scholar@fet.edu",
            defaults={"username": "alex.scholar"},
        )
        student_a.first_name = "Alex"
        student_a.last_name = "Scholar"
        student_a.role = User.Role.STUDENT
        student_a.matricule = "FE24A389"
        student_a.is_email_verified = True
        student_a.department = departments["Computer Engineering"]
        student_a.set_password("student123")
        student_a.save()

        student_b, _ = User.objects.get_or_create(
            email="emma.watson@fet.edu",
            defaults={"username": "emma.watson"},
        )
        student_b.first_name = "Emma"
        student_b.last_name = "Watson"
        student_b.role = User.Role.STUDENT
        student_b.matricule = "FE24B456"
        student_b.is_email_verified = True
        student_b.department = departments["Civil Engineering"]
        student_b.set_password("student123")
        student_b.save()

        created["users"] = {u.email: u.role for u in (admin, lecturer, student_a, student_b)}

        # ---- Courses + ClassSessions ----
        course_specs = [
            ("CEF444", "AI and Machine Learning", "Computer Engineering", lecturer),
            ("CEF450", "Cloud Computing", "Computer Engineering", lecturer),
            ("CEF462", "Digital Image Processing", "Computer Engineering", lecturer),
            ("CEF476", "Software Engineering and Design", "Computer Engineering", lecturer),
            ("SE401", "Advanced Software Engineering", "Computer Engineering", lecturer),
            ("CS301", "Data Structures", "Computer Engineering", lecturer),
            ("ME301", "Thermodynamics II", "Mechanical & Industrial Engineering", lecturer),
        ]
        courses = {}
        for code, name, dept_name, instructor in course_specs:
            course, _ = Course.objects.get_or_create(
                code=code, defaults={"name": name, "department": departments[dept_name]}
            )
            courses[code] = course

        class_sessions = {}
        for code, course in courses.items():
            cs, _ = ClassSession.objects.get_or_create(
                course=course,
                lecturer=lecturer,
                defaults={"starts_at": timezone.now()},
            )
            class_sessions[code] = cs
        created["class_sessions"] = len(class_sessions)

        # ---- Academic calendar ----
        year, _ = SchoolYear.objects.get_or_create(
            name="2025/2026",
            defaults={"start_date": dt.date(2025, 9, 1), "end_date": dt.date(2026, 6, 30)},
        )
        semester, _ = Semester.objects.get_or_create(
            school_year=year,
            name="First Semester",
            defaults={
                "start_date": dt.date(2025, 9, 1),
                "end_date": dt.date(2026, 1, 20),
                "is_current": True,
            },
        )

        # ---- Enrollments (attendance eligibility) ----
        enroll_count = 0
        for matricule in ("FE24A389", "FE24B456"):
            student = User.objects.get(matricule=matricule)
            for code in ("CEF444", "CEF450", "CEF462", "CEF476"):
                _, made = Enrollment.objects.get_or_create(student=student, course=courses[code])
                enroll_count += int(made)
        created["enrollments"] = enroll_count

        # ---- Demo project with one group, task, milestone ----
        project, _ = Project.objects.get_or_create(
            title="FET Platform Integration",
            defaults={"owner": lecturer, "supervisor": lecturer, "created_by": lecturer},
        )
        if project.status == "draft":
            project.status = "active"
            project.is_active = True
            project.save(update_fields=["status", "is_active"])

        group, _ = ProjectGroup.objects.get_or_create(
            project=project, name="Group Alpha", defaults={"leader": student_a, "created_by": lecturer}
        )
        ProjectGroupMembership.objects.get_or_create(
            project=project, group=group, student=student_a, defaults={"assigned_by": lecturer}
        )
        ProjectGroupMembership.objects.get_or_create(
            project=project, group=group, student=student_b, defaults={"assigned_by": lecturer}
        )
        ProjectTask.objects.get_or_create(
            project=project,
            title="Wire frontend to backend",
            defaults={"assignee": student_a, "group": group, "created_by": lecturer},
        )
        ProjectMilestone.objects.get_or_create(
            project=project,
            title="Requirements Gathering",
            defaults={"progress": 100, "due_date": dt.date(2025, 9, 30), "created_by": lecturer},
        )
        created["project"] = project.title

        # ---- Demo announcement (published so it renders) ----
        Announcement.objects.get_or_create(
            title="Welcome to the FET Platform",
            defaults={
                "body": "This account was seeded by manage.py seed_demo.",
                "scope": Announcement.Scope.FACULTY,
                "faculty": faculty,
                "created_by": admin,
                "published_by": admin,
                "is_published": True,
                "published_at": timezone.now(),
            },
        )
        try:
            notify_role_changed(account=student_a, old_role=None, new_role="STUDENT")
        except Exception:  # pragma: no cover - notification fan-out is demo-breadth only
            pass

        self.stdout.write(self.style.SUCCESS("Seed complete."))
        self.stdout.write("Users (all passwords are their demo defaults):")
        for email, role in created["users"].items():
            self.stdout.write(f"  {email}  role={role}")
        self.stdout.write("  admin@fet.local      admin123")
        self.stdout.write("  alida.vance@fet.edu  lecturer123")
        self.stdout.write("  alex.scholar@fet.edu student123")
        self.stdout.write("  emma.watson@fet.edu  student123")
        self.stdout.write(f"Courses: {len(courses)}; class sessions: {created['class_sessions']}")
