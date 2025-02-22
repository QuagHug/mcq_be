# Generated by Django 5.1.2 on 2024-12-25 14:03

import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('mcq_be_app', 'taxonomy_migration'),
    ]

    operations = [
        migrations.RemoveField(
            model_name='taxonomy',
            name='created_at',
        ),
        migrations.RemoveField(
            model_name='taxonomy',
            name='updated_at',
        ),
        migrations.AlterField(
            model_name='question',
            name='question_bank',
            field=models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='questions', to='mcq_be_app.questionbank'),
        ),
        migrations.AlterField(
            model_name='questionbank',
            name='course',
            field=models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='question_banks', to='mcq_be_app.course'),
        ),
    ]
