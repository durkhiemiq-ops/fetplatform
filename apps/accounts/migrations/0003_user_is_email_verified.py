"""Add User.is_email_verified and backfill pre-existing accounts.

Accounts created before the verification gate existed are marked verified in
the same migration: without the backfill, every existing user would be denied
login the moment the gate ships.
"""

from django.db import migrations, models


def mark_pre_existing_users_verified(apps, schema_editor):
    User = apps.get_model("accounts", "User")
    User.objects.filter(is_email_verified=False).update(is_email_verified=True)


class Migration(migrations.Migration):

    dependencies = [
        ("accounts", "0002_user_matricule_user_staffid"),
    ]

    operations = [
        migrations.AddField(
            model_name="user",
            name="is_email_verified",
            field=models.BooleanField(
                default=False,
                help_text="Set once the address has confirmed a one-time code.",
            ),
        ),
        migrations.RunPython(
            mark_pre_existing_users_verified,
            migrations.RunPython.noop,
        ),
    ]
