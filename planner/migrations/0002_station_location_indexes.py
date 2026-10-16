# Generated manually for the assessment improvements.

from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("planner", "0001_initial")]

    operations = [
        migrations.AddField(
            model_name="fuelstation",
            name="location_source",
            field=models.CharField(default="city_centroid", max_length=30),
        ),
        migrations.AlterField(
            model_name="fuelstation",
            name="latitude",
            field=models.FloatField(db_index=True),
        ),
        migrations.AlterField(
            model_name="fuelstation",
            name="longitude",
            field=models.FloatField(db_index=True),
        ),
        migrations.AlterField(
            model_name="fuelstation",
            name="state",
            field=models.CharField(db_index=True, max_length=10),
        ),
    ]
