import uuid

from django.contrib.auth.models import AbstractBaseUser, BaseUserManager, PermissionsMixin
from django.db import models


class UserManager(BaseUserManager):
    def create_user(self, email, username, first_name, last_name, password=None, **extra_fields):
        if not email:
            raise ValueError("Email is required")
        if not username:
            raise ValueError("Username is required")
        email = self.normalize_email(email)
        user = self.model(
            email=email,
            username=username,
            first_name=first_name,
            last_name=last_name,
            **extra_fields,
        )
        user.set_password(password)
        user.save(using=self._db)
        return user

    def create_superuser(self, email, username, first_name, last_name, password=None, **extra_fields):
        extra_fields.setdefault("is_staff", True)
        extra_fields.setdefault("is_superuser", True)
        extra_fields.setdefault("role", "ADMINISTRATOR")
        # CLI-created superusers must not be locked out behind the
        # email-verification gate they administer.
        extra_fields.setdefault("is_email_verified", True)
        return self.create_user(email, username, first_name, last_name, password, **extra_fields)

    def get_by_natural_key(self, email):
        """Allow authentication by email, matricule, or staffid."""
        return self.get(
            models.Q(email__iexact=email)
            | models.Q(matricule__iexact=email)
            | models.Q(staffid__iexact=email)
        )


class User(AbstractBaseUser, PermissionsMixin):
    class Role(models.TextChoices):
        STUDENT = "STUDENT", "Student"
        LECTURER = "LECTURER", "Lecturer"
        ADMINISTRATOR = "ADMINISTRATOR", "Administrator"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    email = models.EmailField(unique=True, db_index=True)
    username = models.CharField(unique=True, max_length=150)
    first_name = models.CharField(max_length=150)
    last_name = models.CharField(max_length=150)
    matricule = models.CharField(
        max_length=50,
        unique=True,
        null=True,
        blank=True,
        db_index=True,
        help_text="Student matricule number (assigned on enrollment).",
    )
    staffid = models.CharField(
        max_length=50,
        unique=True,
        null=True,
        blank=True,
        db_index=True,
        help_text="Staff / employee number (assigned by administration).",
    )
    role = models.CharField(
        max_length=20,
        choices=Role.choices,
        default=Role.STUDENT,
    )
    is_active = models.BooleanField(default=True)
    is_staff = models.BooleanField(default=False)
    is_email_verified = models.BooleanField(
        default=False,
        help_text="Set once the address has confirmed a one-time code.",
    )
    faculty = models.ForeignKey(
        "academic.Faculty",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
    )
    department = models.ForeignKey(
        "academic.Department",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    objects = UserManager()

    USERNAME_FIELD = "email"
    REQUIRED_FIELDS = ["username", "first_name", "last_name"]

    class Meta:
        db_table = "accounts_user"
        ordering = ["-created_at"]

    def __str__(self):
        return self.email
