# Generated by Django 5.1.3 on 2025-03-12 12:56

import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('mcq_be_app', '0003_remove_questiontaxonomy_difficulty'),
    ]

    operations = [
        migrations.RemoveField(
            model_name='questionbank',
            name='is_child',
        ),
        migrations.AddField(
            model_name='questionbank',
            name='parent',
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.CASCADE, related_name='children', to='mcq_be_app.questionbank'),
        ),
    ]
