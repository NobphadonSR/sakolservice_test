from django.urls import path
from . import views
from django.conf import settings
from django.conf.urls.static import static

app_name = 'service'

urlpatterns = [
    # URLs สำหรับลูกค้า
    path('list/', views.ServiceRequestListView.as_view(), name='request_list'),
    path('create/', views.CreateServiceRequestView.as_view(), name='create_request'),
    path('request/<int:pk>/', views.ServiceRequestDetailView.as_view(), name='request_detail'),
    path('request/<int:request_id>/advice/', views.submit_technician_advice, name='submit_advice'),
    path('request/<int:request_id>/confirm/', views.confirm_service_request, name='confirm_request'),
    path('request/<int:pk>/assign-technician/', views.assign_technician, name='assign_technician'),
    path('request/<int:pk>/accept/', views.accept_request, name='accept_request'),
    path('request/<int:pk>/confirm-advice/', views.confirm_advice, name='confirm_advice'),
    path('proposal/<int:proposal_id>/approve/', views.approve_proposal, name='approve_proposal'),
    
    # URLs สำหรับฝ่ายบริการ
    path('dashboard/', views.DashboardView.as_view(), name='dashboard'),
    path('records/', views.ServiceRecordListView.as_view(), name='service_records'),
    path('records/create/', views.ServiceRecordCreateView.as_view(), name='create_record'),
    path('records/<int:pk>/', views.ServiceRecordDetailView.as_view(), name='record_detail'),
    path('records/<int:pk>/edit/', views.ServiceRecordUpdateView.as_view(), name='record_edit'),
    path('records/<int:pk>/delete/', views.ServiceRecordDeleteView.as_view(), name='record_delete'),
    path('technician/daily-summary/', views.TechnicianDailySummaryView.as_view(), name='technician_daily_summary'),
    path('approve-proposal/<int:proposal_id>/', views.approve_proposal, name='approve_proposal'),
    path('submit-recommendation/<int:service_id>/', views.submit_service_recommendation, name='submit_recommendation'),
    path('update-job-status/<int:service_id>/', views.update_job_status, name='update_job_status'),
    path('generate-bill/<int:service_id>/', views.generate_bill, name='generate_bill'),
    path('request/<int:request_id>/customer-confirm/', views.confirm_customer_request, name='customer_confirm_request'),
    path('request/<int:request_id>/set-cost/', views.set_service_cost, name='set_service_cost'),
    path('request/<int:request_id>/update-status/', views.update_service_status, name='update_service_status'),

    # URLs สำหรับช่าง
    path('technician/calendar/', views.TechnicianCalendarView.as_view(), name='technician_calendar'),
    path('technician/get-events/', views.get_technician_events, name='get_technician_events'),
    path('technician/task/<int:pk>/', views.TechnicianTaskDetailView.as_view(), name='task_detail'),
    path('technician/recommend/<int:service_id>/', views.submit_service_recommendation, name='submit_recommendation'),
    path('technician/status/update/<int:service_id>/', views.update_job_status, name='update_job_status'),
    path('request/<int:service_id>/update-status/', views.update_service_status, name='update_service_status'),
    path('image/<int:image_id>/delete/', views.delete_service_image, name='delete_service_image'),

    # URLs ฟีเจอร์สำหรับฝ่ายบริการ
    path('manage/', views.ServiceRequestManageView.as_view(), name='manage_requests'),
    path('manage/export/', views.export_service_requests, name='export_service_requests'),
    path('update-status/<int:pk>/', views.UpdateServiceStatusView.as_view(), name='update_status'),
    path('customer-map/', views.CustomerMapView.as_view(), name='customer_map'),
    path('request/<int:pk>/warranty/', views.manage_warranty, name='manage_warranty'),
    path('upload-excel/', views.upload_excel, name='upload_excel'),
    path('download-template/', views.download_template, name='download_template'),
] + static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT) + static(settings.STATIC_URL, document_root=settings.STATIC_ROOT)