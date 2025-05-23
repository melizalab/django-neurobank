# Generated by Django 4.1.5 on 2023-01-20 21:11

from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("nbank_registry", "0005_datatype_downloadable"),
    ]

    operations = [
        migrations.AlterField(
            model_name="archive",
            name="id",
            field=models.AutoField(primary_key=True, serialize=False),
        ),
        migrations.AlterField(
            model_name="datatype",
            name="id",
            field=models.AutoField(primary_key=True, serialize=False),
        ),
        migrations.AlterField(
            model_name="location",
            name="id",
            field=models.AutoField(primary_key=True, serialize=False),
        ),
        migrations.AlterField(
            model_name="resource",
            name="metadata",
            field=models.JSONField(blank=True, null=True),
        ),
    ]
