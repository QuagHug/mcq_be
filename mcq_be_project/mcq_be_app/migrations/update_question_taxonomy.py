from django.db import migrations, models

class Migration(migrations.Migration):
    dependencies = [
        ('mcq_be_app', '0001_remove_taxonomy_created_at_and_more'),
    ]

    operations = [
        migrations.AlterField(
            model_name='questiontaxonomy',
            name='level',
            field=models.CharField(max_length=255),  # Change from IntegerField to CharField
        ),
    ] 