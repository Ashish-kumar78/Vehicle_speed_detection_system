from django.db import models

class VehicleRecord(models.Model):
    VEHICLE_TYPES = (
        ('car', 'car'),
        ('truck', 'truck'),
        ('bike', 'bike'),
        ('bus', 'bus'),
    )
    STATUS_CHOICES = (
        ('overspeed', 'overspeed'),
        ('normal', 'normal'),
    )
    
    vehicle_number = models.CharField(max_length=20)
    vehicle_type = models.CharField(max_length=10, choices=VEHICLE_TYPES)
    speed_kmh = models.FloatField()
    status = models.CharField(max_length=15, choices=STATUS_CHOICES)
    timestamp = models.DateTimeField(auto_now_add=True)
    violation_count = models.IntegerField(default=0)
    distance_m = models.FloatField()

    class Meta:
        db_table = 'vehicle_records'
        verbose_name = 'Vehicle Record'
        verbose_name_plural = 'Vehicle Records'

    def __str__(self):
        return f"{self.vehicle_number} ({self.speed_kmh} km/h)"

class SystemSetting(models.Model):
    speed_limit = models.FloatField(default=60.0, help_text="Speed limit in km/h")
    distance_calibration = models.FloatField(default=10.0, help_text="Distance between detection lines in meters")
    admin_email = models.EmailField(default="admin@gmail.com")
    
    class Meta:
        db_table = 'system_settings'
        verbose_name = 'System Setting'
        verbose_name_plural = 'System Settings'

    def __str__(self):
        return f"Config (Limit: {self.speed_limit}km/h)"
