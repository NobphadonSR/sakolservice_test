from django.contrib import admin
from .models import ServiceRequest, TechnicianResponse, TechnicianJobStatus, ServiceImage, ServiceRecord

admin.site.register(ServiceRequest)
admin.site.register(TechnicianResponse)
admin.site.register(TechnicianJobStatus)
admin.site.register(ServiceImage)
admin.site.register(ServiceRecord)