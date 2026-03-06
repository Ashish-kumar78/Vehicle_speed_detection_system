from django.contrib import admin
from .models import VehicleRecord, SystemSetting

@admin.register(VehicleRecord)
class VehicleRecordAdmin(admin.ModelAdmin):
    list_display = ('vehicle_number', 'vehicle_type', 'speed_kmh', 'status', 'timestamp', 'violation_count')
    list_filter = ('status', 'vehicle_type')
    search_fields = ('vehicle_number',)

@admin.register(SystemSetting)
class SystemSettingAdmin(admin.ModelAdmin):
    list_display = ('speed_limit', 'distance_calibration', 'admin_email')

    def has_add_permission(self, request):
        if self.model.objects.count() >= 1:
            return False
        return super().has_add_permission(request)
