from django.db import migrations, models

class Migration(migrations.Migration):
    dependencies = [
        ('mcq_be_app', '0002_userprofile'),
    ]

    operations = [
        migrations.AddField(
            model_name='Answer',
            name='explanation',
            field=models.TextField(blank=True, null=True),
        ),
    ] 