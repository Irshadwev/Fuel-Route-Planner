from django.db import models

# Create your models here.
class FuelStation(models.Model):
    # Data from the CSV file
    station_id = models.CharField(max_length=20, unique=True)
    name = models.CharField(max_length=200)
    address = models.CharField(max_length=255)
    city = models.CharField(max_length=100)
    state = models.CharField(max_length=10)
    price = models.FloatField()  # price per gallon

    # Map pin, added by the load_stations command 
    latitude = models.FloatField()
    longitude = models.FloatField()

    def __str__(self):
        return f"{self.name} - {self.city}, {self.state}"
