# Generated by Django 5.1.3 on 2025-03-21 17:26

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('mcq_be_app', '0007_testresult'),
    ]

    operations = [
        migrations.AddField(
            model_name='question',
            name='statistics',
            field=models.JSONField(default=dict),
        ),
    ]
