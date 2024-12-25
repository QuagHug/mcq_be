from django.db import migrations, models

class Migration(migrations.Migration):
    dependencies = [
        ('mcq_be_app', 'update_question_taxonomy'),
    ]

    operations = [
        migrations.AddField(
            model_name='questiontaxonomy',
            name='difficulty',
            field=models.CharField(
                choices=[('easy', 'Easy'), ('medium', 'Medium'), ('hard', 'Hard')],
                default='medium',
                max_length=10
            ),
        ),
    ] 