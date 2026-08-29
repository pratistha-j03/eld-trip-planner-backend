from django.db import models


class Trip(models.Model):


    current_location = models.CharField(max_length=255)
    pickup_location = models.CharField(max_length=255)
    dropoff_location = models.CharField(max_length=255)
    current_cycle_used_hours = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        help_text="Hours already used in the driver's current 70hrs/8days cycle.",
    )

    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f'{self.pickup_location} -> {self.dropoff_location} ({self.created_at:%Y-%m-%d})'
