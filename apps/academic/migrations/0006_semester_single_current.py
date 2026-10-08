from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("academic", "0005_department_code"),
    ]

    operations = [
        migrations.AddConstraint(
            model_name="semester",
            constraint=models.UniqueConstraint(
                fields=("is_current",),
                condition=models.Q(("is_current", True)),
                name="single_current_semester",
            ),
        ),
    ]
