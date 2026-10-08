"""Development demo seed: ``manage.py seed_demo``.

Idempotent (keyed on natural keys) so it is safe to re-run. Creates every row
the frontend needs to be meaningfully alive on first login:

- Faculty + Departments + Courses (codes match the frontend catalogue)
- One SUPERUSER admin, one LECTURER, two STUDENTs — all with
  ``is_email_verified=True`` (bypassing the OTP gate deliberately in seed data;
  BR-209 is a product-environment gate, not a demo impediment)
- SchoolYear + a current Semester whose window contains today
- ClassSession (the anchor for all attendance)
- One CourseOffering per demo course, taught by the demo lecturer, each with
  one class definition (API §22) — this is what ``GET /lecturers/me/courses/``
  reads, so without it the lecturer's workspace opens empty
- Enrollment rows linking students to courses, each pointing at that offering —
  ``GET /students/me/courses/`` only returns enrollments that carry an offering,
  so offering-less legacy rows leave the student's workspace empty too
- One demo Project with tasks, a group, and a milestone
- One Announcement and one Notification

**Never run against production settings.**

Passwords are printed at the end and are deterministic for the demo.
"""

from __future__ import annotations

from django.core.management.base import BaseCommand, CommandError
from django.utils import timezone

from apps.academic.models import (
    ClassSchedule,
    ClassSession,
    Course,
    CourseOffering,
    Department,
    Enrollment,
    Faculty,
    SchoolYear,
    Semester,
)
from apps.academic.services.structure_service import create_class_definition
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

        student_a, made_a = User.objects.get_or_create(
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

        # ---- Current term ----
        # The platform only asks for a semester flagged ``is_current``; the real
        # term boundaries and registration windows are an institutional policy
        # this repository does not specify (reported in
        # docs/mvp-integration-context.md, not invented here). The demo keeps a
        # single current term that always contains today, on a three-term
        # convention so no date is ever left uncovered, and lets
        # ``Semester.save()`` retire the lapsed term it supersedes.
        today = timezone.localdate()
        current_semester = Semester.objects.filter(is_current=True).first()
        if current_semester is None or not (
            current_semester.start_date <= today <= current_semester.end_date
        ):
            if today.month >= 9:
                term_name = "First Semester"
                term_start = dt.date(today.year, 9, 1)
                term_end = dt.date(today.year, 12, 31)
                year_start = today.year
            elif today.month <= 4:
                term_name = "Second Semester"
                term_start = dt.date(today.year, 1, 1)
                term_end = dt.date(today.year, 4, 30)
                year_start = today.year - 1
            else:
                term_name = "Summer Semester"
                term_start = dt.date(today.year, 5, 1)
                term_end = dt.date(today.year, 8, 31)
                year_start = today.year - 1
            school_year, _ = SchoolYear.objects.get_or_create(
                name=f"{year_start}/{year_start + 1}",
                defaults={
                    "start_date": dt.date(year_start, 9, 1),
                    "end_date": dt.date(year_start + 1, 8, 31),
                },
            )
            current_semester, _ = Semester.objects.get_or_create(
                school_year=school_year,
                name=term_name,
                defaults={"start_date": term_start, "end_date": term_end},
            )
            # Re-running after the term rolls over refreshes the window instead
            # of leaving the lapsed dates authoritative.
            current_semester.start_date = term_start
            current_semester.end_date = term_end
            current_semester.is_current = True
            current_semester.save()
        if (
            current_semester.registration_deadline is None
            or current_semester.registration_deadline < today
        ):
            current_semester.registration_deadline = min(
                current_semester.end_date, today + dt.timedelta(days=30)
            )
            current_semester.save()
        created["semester"] = f"{current_semester} (deadline {current_semester.registration_deadline})"

        # ---- Course offerings + class definitions ----
        # Courses and legacy ClassSessions alone left both demo roles staring
        # at empty lists: the lecturer view reads CourseOffering, the student
        # view reads enrollments that carry one. One offering per demo course
        # under the current term, taught by the demo lecturer, each given a
        # single class definition — the Decision A meaning of "Create class",
        # never a ClassSession and never a roster copy.
        offerings = {}
        class_definitions = 0
        slots = [
            ("MONDAY", dt.time(8, 0), dt.time(9, 30)),
            ("TUESDAY", dt.time(10, 0), dt.time(11, 30)),
            ("WEDNESDAY", dt.time(13, 0), dt.time(14, 30)),
            ("THURSDAY", dt.time(8, 0), dt.time(9, 30)),
            ("FRIDAY", dt.time(10, 0), dt.time(11, 30)),
        ]
        for index, (code, course) in enumerate(courses.items()):
            offering, _ = CourseOffering.objects.get_or_create(
                course=course,
                semester=current_semester,
                defaults={
                    "department": course.department,
                    "lecturer": lecturer,
                    "status": "ACTIVE",
                    "registration_deadline": current_semester.registration_deadline,
                },
            )
            offerings[code] = offering
            if offering.lecturer_id != lecturer.pk:
                # Someone else's offering: the seed never steals ownership, and
                # it could not author a class under it anyway.
                continue
            if offering.schedules.filter(is_active=True).exists():
                continue
            day, start, end = slots[index % len(slots)]
            create_class_definition(
                actor=lecturer,
                offering=offering,
                data={
                    "name": f"{code} Lecture",
                    "class_type": ClassSchedule.ClassType.LECTURE,
                    "location": "Demo Lecture Hall",
                    "day_of_week": day,
                    "start_time": start,
                    "end_time": end,
                },
            )
            class_definitions += 1
        created["offerings"] = len(offerings)
        created["class_definitions"] = class_definitions

        # ---- Enrollments (attendance eligibility) ----
        enroll_count = 0
        offering_attached = 0
        for matricule in ("FE24A389", "FE24B456"):
            student = User.objects.get(matricule=matricule)
            for code in ("CEF444", "CEF450", "CEF462", "CEF476"):
                enrollment, made = Enrollment.objects.get_or_create(
                    student=student, course=courses[code]
                )
                enroll_count += int(made)
                # A legacy row that carries no offering is invisible to
                # ``GET /students/me/courses/``. Attach the demo offering so the
                # student's classroom list renders, unless the row was dropped
                # (BR-014: the seed never resurrects a drop) or another row
                # already holds this offering.
                if (
                    enrollment.course_offering_id is not None
                    or enrollment.dropped_at is not None
                    or not enrollment.is_active
                    or code not in offerings
                ):
                    continue
                if Enrollment.objects.filter(
                    student=student, course_offering=offerings[code]
                ).exists():
                    continue
                enrollment.course_offering = offerings[code]
                enrollment.save(update_fields=["course_offering", "updated_at"])
                offering_attached += 1
        created["enrollments"] = enroll_count
        created["offering_enrollments"] = offering_attached

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
            # The seed is idempotent and re-runnable: only announce the role
            # on first creation, otherwise every run spams a duplicate.
            if made_a:
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
        self.stdout.write(f"Current semester: {created['semester']}")
        self.stdout.write(
            f"Offerings: {created['offerings']}; "
            f"class definitions: {created['class_definitions']}; "
            f"enrollments attached to an offering: {created['offering_enrollments']}"
        )
