# Generated by Django 5.1.2 on 2024-12-07 08:38

import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('mcq_be_app', '0002_merge_course_migration_new_migration'),
    ]

    operations = [
        migrations.AlterField(
            model_name='questionbank',
            name='course',
            field=models.ForeignKey(
                on_delete=django.db.models.deletion.CASCADE,
                related_name='question_banks',
                to='mcq_be_app.course',
                null=True
            ),
        ),
    ]
