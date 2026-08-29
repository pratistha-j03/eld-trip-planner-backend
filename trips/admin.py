from django.contrib import admin

from .models import Trip


@admin.register(Trip)
class TripAdmin(admin.ModelAdmin):
    list_display = [
        'id',
        'current_location',
        'pickup_location',
        'dropoff_location',
        'current_cycle_used_hours',
        'created_at',
    ]
    readonly_fields = ['created_at']
