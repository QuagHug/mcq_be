from django.db import migrations

class Migration(migrations.Migration):
    dependencies = [
        ('mcq_be_app', '0002_rename_created_by_course_owner'),
    ]

    operations = [
        migrations.RemoveField(
            model_name='questiontaxonomy',
            name='difficulty',
        ),
    ]