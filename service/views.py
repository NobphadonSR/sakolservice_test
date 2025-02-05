# Library ที่เรียกใช้ทั้งหมด
import os
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.views.generic import ListView, DetailView, TemplateView, CreateView, UpdateView, DeleteView
from django.contrib.auth.mixins import UserPassesTestMixin, LoginRequiredMixin
from django.urls import reverse_lazy
from django.http import JsonResponse, HttpResponseForbidden, HttpResponseRedirect
from django.db.models import Sum, Q
from datetime import datetime, timedelta
import pandas as pd
from .models import (
    ServiceRequest, 
    TechnicianProposal, 
    ServiceRecord,
    TechnicianJobStatus, 
    ServiceImage,
    ServiceRecordHistory
)
from accounts.models import Customer
from .forms import ServiceRequestForm, ServiceRecordForm
from django.utils import timezone
from accounts.models import User
from django.views.generic.detail import BaseDetailView
from django.contrib import messages
from django.core.exceptions import ValidationError
from django.http import JsonResponse, HttpResponse
from django.views.decorators.http import require_POST
from openpyxl import Workbook
import io
from decimal import Decimal
from django.contrib.auth import get_user_model
from django.forms import model_to_dict

User = get_user_model()

# หน้าแรก
class HomeView(TemplateView):
    template_name = 'service/home.html'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        if self.request.user.is_authenticated:
            context['user_type'] = self.request.user.user_type
        return context

# มอบหมายงานให้กับช่าง
@login_required
def assign_technician(request, pk):
    if request.method == 'POST' and request.user.user_type == 'service':
        service_request = get_object_or_404(ServiceRequest, pk=pk)
        technician_id = request.POST.get('technician')
        
        if technician_id:
            try:
                technician = User.objects.get(id=technician_id, user_type='technician')
                service_request.technician = technician
                service_request.status = 'assigned'
                service_request.save()
                
                # สร้างประวัติการมอบหมายงาน
                TechnicianJobStatus.objects.create(
                    service_request=service_request,
                    technician=technician,
                    status='assigned',
                    notes='มอบหมายงานโดยฝ่ายบริการ'
                )
                
                messages.success(request, f'มอบหมายงานให้ช่าง {technician.username} เรียบร้อยแล้ว')
                
                # ตรวจสอบว่าเป็น AJAX request หรือไม่
                if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
                    return JsonResponse({
                        'status': 'success',
                        'message': f'มอบหมายงานให้ช่าง {technician.username} เรียบร้อยแล้ว'
                    })
                
            except User.DoesNotExist:
                if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
                    return JsonResponse({
                        'status': 'error',
                        'message': 'ไม่พบข้อมูลช่างที่เลือก'
                    }, status=404)
                messages.error(request, 'ไม่พบข้อมูลช่างที่เลือก')
        else:
            if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
                return JsonResponse({
                    'status': 'error',
                    'message': 'กรุณาเลือกช่าง'
                }, status=400)
            messages.error(request, 'กรุณาเลือกช่าง')
    
    # สำหรับ non-AJAX requests หรือเมื่อเสร็จสิ้นการทำงาน
    return redirect('service:request_detail', pk=pk)
# ตรวจสอบสิทธิ์การเข้าถึงข้อมูล
class ServiceStaffRequired(UserPassesTestMixin):
    def test_func(self):
        return self.request.user.user_type == 'service'

# ตรวจสอบสิทธิ์การเข้าถึงข้อมูลช่าง
class TechnicianRequired(UserPassesTestMixin):
    def test_func(self):
        return self.request.user.user_type == 'technician'
    

class CreateServiceRequestView(LoginRequiredMixin, CreateView):
    model = ServiceRequest
    form_class = ServiceRequestForm
    template_name = 'service/create_request.html'
    success_url = reverse_lazy('service:request_list')

    def form_valid(self, form):
        try:
            # กำหนดค่าพื้นฐาน
            customer = self.request.user.customer
            form.instance.customer = customer
            form.instance.status = 'pending'
            form.instance.need_advice = False
            
            # ค้นหาข้อมูลที่ตรงกันใน ServiceRecord
            matching_record = ServiceRecord.objects.filter(
                project_name=customer.project_name,
                house_number=customer.house_number
            ).first()

            # บันทึก ServiceRequest
            response = super().form_valid(form)
            
            # สร้าง ServiceRecord
            if matching_record:
                # ถ้ามีข้อมูลตรงกัน ใช้ข้อมูลเดิมและอัพเดทเฉพาะส่วนที่จำเป็น
                service_record = ServiceRecord.objects.create(
                    customer=customer,
                    description=form.instance.description,
                    date=form.instance.appointment_date,
                    time=form.instance.appointment_time,
                    # ข้อมูลจาก matching record
                    project_name=matching_record.project_name,
                    house_number=matching_record.house_number,
                    project_code=matching_record.project_code,
                    plot_number=matching_record.plot_number,
                    house_type=matching_record.house_type,
                    transfer_date=matching_record.transfer_date,
                    warranty_expiry=matching_record.warranty_expiry,
                    # ข้อมูลปัจจุบัน
                    customer_name=customer.user.get_full_name() or customer.user.username,
                    customer_phone=customer.phone,
                    status='pending'
                )
            else:
                # ถ้าไม่มีข้อมูลตรงกัน สร้างใหม่
                service_record = ServiceRecord.objects.create(
                    customer=customer,
                    description=form.instance.description,
                    date=form.instance.appointment_date,
                    time=form.instance.appointment_time,
                    project_name=customer.project_name,
                    house_number=customer.house_number,
                    customer_name=customer.user.get_full_name() or customer.user.username,
                    customer_phone=customer.phone,
                    status='pending'
                )

            # เชื่อมโยง ServiceRequest กับ ServiceRecord
            form.instance.service_record = service_record
            form.instance.save()
            
            messages.success(self.request, 'บันทึกการแจ้งซ่อมเรียบร้อยแล้ว')
            return response
            
        except Exception as e:
            messages.error(self.request, f'เกิดข้อผิดพลาด: {str(e)}')
            return super().form_invalid(form)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        customer = self.request.user.customer
        if customer:
            context.update({
                'customer': customer,
                'customer_name': customer.user.username,
                'project_name': customer.project_name,
                'house_number': customer.house_number,
                'phone': customer.phone,
                'today': timezone.now().date(),
            })
        return context

    def get_form(self, form_class=None):
        form = super().get_form(form_class)
        
        # เพิ่มคำอธิบายที่ชัดเจน
        form.fields['description'].help_text = 'กรุณาระบุอาการหรือปัญหาที่พบให้ชัดเจน'
        form.fields['appointment_date'].help_text = 'เลือกวันที่สะดวกให้ช่างเข้าตรวจสอบ'
        form.fields['appointment_time'].help_text = 'กรุณาเลือกเวลานัดหมายระหว่าง ตอนเช้า 10:00-10:30 ตอนบ่าย 14:00-14:30'
        
        return form
'''
# สร้างงานใหม่
class CreateServiceRequestView(LoginRequiredMixin, CreateView):
    model = ServiceRequest
    form_class = ServiceRequestForm
    template_name = 'service/create_request.html'
    success_url = reverse_lazy('service:request_list')

    def form_valid(self, form):
        try:
            # กำหนดค่าพื้นฐาน
            form.instance.customer = self.request.user.customer
            form.instance.status = 'pending'
            form.instance.need_advice = False
            
            # บันทึกข้อมูล
            response = super().form_valid(form)
            
            # ส่งข้อความยืนยัน
            messages.success(self.request, 'บันทึกการแจ้งซ่อมเรียบร้อยแล้ว')
            
            return response
            
        except Exception as e:
            messages.error(self.request, f'เกิดข้อผิดพลาด: {str(e)}')
            return super().form_invalid(form)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        customer = self.request.user.customer
        if customer:
            context.update({
                'customer': customer,
                'customer_name': customer.user.username,
                'project_name': customer.project_name,
                'house_number': customer.house_number,
                'phone': customer.phone,
                'today': timezone.now().date(),
            })
        return context

    def get_form(self, form_class=None):
        form = super().get_form(form_class)
        # ซ่อนฟิลด์ที่ไม่จำเป็นสำหรับลูกค้า
        form.fields['need_advice'].widget = forms.HiddenInput()
        form.fields['service_level'].required = False
        form.fields['ac_count'].required = False
        
        # เพิ่มคำอธิบายที่ชัดเจน
        form.fields['description'].help_text = 'กรุณาระบุอาการหรือปัญหาที่พบให้ชัดเจน'
        form.fields['appointment_date'].help_text = 'เลือกวันที่สะดวกให้ช่างเข้าตรวจสอบ'
        form.fields['appointment_time'].help_text = 'เลือกช่วงเวลาที่สะดวก (8:00-17:00)'
        
        return form
'''
class ServiceRequestListView(LoginRequiredMixin, ListView):
    model = ServiceRequest
    template_name = 'service/request_list.html'
    context_object_name = 'requests'
    paginate_by = 10

    def get_queryset(self):
        user = self.request.user
        queryset = ServiceRequest.objects.all()  # เปลี่ยนจาก ServiceRecord เป็น ServiceRequest
        
        if user.user_type == 'customer':
            # ลูกค้าเห็นเฉพาะงานของตัวเอง
            queryset = queryset.filter(customer=user.customer)
        elif user.user_type == 'technician':
            # ช่างเห็นเฉพาะงานที่ได้รับมอบหมาย
            queryset = queryset.filter(technician=user)
        elif user.user_type == 'service':
            # ฝ่ายบริการเห็นทุกงาน
            queryset = queryset.all()
        else:
            queryset = ServiceRequest.objects.none()
            
        # เพิ่ม select_related เพื่อลดจำนวนการ query
        return queryset.select_related(
            'customer',
            'customer__user',
            'technician',
            'service_record'  # เพิ่ม service_record
        ).order_by('-created_at')  # ServiceRequest มี created_at

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        
        # เพิ่มข้อมูลสถานะสำหรับ badge
        context['status_colors'] = {
            'pending': 'warning',
            'confirmed': 'info', 
            'assigned': 'primary',
            'accepted': 'info',
            'traveling': 'primary',
            'arrived': 'purple',
            'fixing': 'orange',
            'completed': 'success',
            'cancelled': 'danger',
            'rescheduled': 'warning'
        }
        return context

# ดูรายละเอียดงาน
class ServiceRequestDetailView(LoginRequiredMixin, DetailView):
    model = ServiceRequest
    template_name = 'service/request_detail.html'
    context_object_name = 'request'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)

        # เพิ่มบรรทัดนี้เพื่อดึงรายชื่อช่าง
        context['available_technicians'] = User.objects.filter(
            user_type='technician', 
            is_active=True
        ).select_related('customer').order_by('first_name')
        
        service_request = self.object
        context.update({
            'service_proposals': service_request.service_proposals.select_related(
                'technician'
            ).order_by('-created_at'),
            'technician_proposals': service_request.technician_proposals.select_related(
                'technician'
            ).order_by('-created_at'),
            'job_statuses': TechnicianJobStatus.objects.filter(
                service_request=service_request
            ).select_related('technician').order_by('-created_at'),
            'service_images': ServiceImage.objects.filter(
                service_request=service_request
            ).order_by('-uploaded_at')
        })
        
        return context

    def get_queryset(self):
        user = self.request.user
        base_queryset = ServiceRequest.objects.select_related(
            'customer',
            'customer__user',
            'technician',
            'service_record'
        )
        
        if user.user_type == 'customer':
            return base_queryset.filter(customer=user.customer)
        elif user.user_type in ['service', 'technician']:
            return base_queryset.all()
            
        return ServiceRequest.objects.none()

# หน้า Dashboard ของฝ่ายบริการ
class DashboardView(LoginRequiredMixin, TemplateView):
    template_name = 'service/dashboard.html'
    
    def dispatch(self, request, *args, **kwargs):
        if request.user.user_type != 'service':
            return HttpResponseForbidden('คุณไม่มีสิทธิ์เข้าถึงหน้านี้')
        return super().dispatch(request, *args, **kwargs)
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        
        # ดึงข้อมูลงานที่รอดำเนินการ
        context['pending_records'] = ServiceRequest.objects.filter(
            status__in=['pending', 'new']
        ).select_related('customer').order_by('-created_at')

        # ดึงข้อมูลงานที่กำลังดำเนินการ
        context['in_progress_records'] = ServiceRequest.objects.filter(
            status__in=['assigned', 'accepted','traveling', 'arrived', 'fixing']
        ).select_related('technician').order_by('-created_at')

        # ข้อมูลกราฟ
        period = self.request.GET.get('period', 'month')
        today = timezone.now()
        
        if period == 'day':
            start_date = today - timedelta(days=7)
            date_format = '%Y-%m-%d'
        elif period == 'week':
            start_date = today - timedelta(weeks=4)
            date_format = '%Y-%W'
        elif period == 'year':
            start_date = today - timedelta(days=365)
            date_format = '%Y-%m'
        else:  # month
            start_date = today - timedelta(days=30)
            date_format = '%Y-%m-%d'

        # ใช้ Django ORM แทน raw SQL
        issues = ServiceRequest.objects.filter(
            created_at__gte=start_date
        ).order_by('created_at')

        # จัดกลุ่มข้อมูลตามวันที่
        data_points = {}
        for issue in issues:
            if period == 'day':
                date_key = issue.created_at.strftime('%d/%m')
            elif period == 'week':
                date_key = f"W{issue.created_at.strftime('%W')}"
            elif period == 'year':
                date_key = issue.created_at.strftime('%m/%Y')
            else:  # month
                date_key = issue.created_at.strftime('%d/%m')
            
            data_points[date_key] = data_points.get(date_key, 0) + 1

        # เรียงข้อมูลตามวันที่แบบย้อนกลับ
        sorted_data = sorted(data_points.items(), key=lambda x: (
            int(x[0].split('/')[1]) if '/' in x[0] else 0,  # เดือน
            int(x[0].split('/')[0]) if '/' in x[0] else int(x[0].replace('W', ''))  # วันหรือสัปดาห์
        ))
        
        context['issues_labels'] = [item[0] for item in sorted_data]
        context['issues_data'] = [item[1] for item in sorted_data]

        if not context['issues_labels']:
            context['issues_labels'] = ['ไม่มีข้อมูล']
            context['issues_data'] = [0]
        
        return context

# ดูรายการบันทึกงาน
from django.contrib.auth.mixins import UserPassesTestMixin

class ServiceRecordListView(LoginRequiredMixin, UserPassesTestMixin, ListView):
    model = ServiceRecord
    template_name = 'service/record_list.html'
    context_object_name = 'records'
    paginate_by = 100

    def test_func(self):
        return self.request.user.user_type == 'service'

    def get_queryset(self):
        queryset = super().get_queryset()
        search_query = self.request.GET.get('search')
        
        if search_query:
            queryset = queryset.filter(
                Q(customer_name__icontains=search_query) |  # ค้นหาจากชื่อผู้ใช้
                Q(job_number__icontains=search_query) |     # ค้นหาจากเลขที่งาน
                Q(customer__phone__icontains=search_query) | # ค้นหาจากเบอร์โทร
                Q(project_code__icontains=search_query) |   # ค้นหาจากรหัสโครงการ
                Q(project_name__icontains=search_query) |   # ค้นหาจากชื่อโครงการ
                Q(house_number__icontains=search_query)     # ค้นหาจากห้องหมายเลข
            )
        
        # เปลี่ยนจาก order_by('sequence') เป็น order_by('year', 'month', 'job_number')
        return queryset.order_by('year', 'month', 'job_number')
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        
        # คำนวณลำดับเริ่มต้นสำหรับแต่ละหน้า
        page_number = self.request.GET.get('page', 1)
        context['start_index'] = (int(page_number) - 1) * self.paginate_by
        
        # เพิ่มข้อมูลสำหรับการแสดงผล
        context['total_records'] = self.get_queryset().count()
        context['current_page'] = page_number
        
        # สร้างรายการลำดับสำหรับแต่ละรายการในหน้าปัจจุบัน
        records_with_index = []
        for index, record in enumerate(context['records'], start=context['start_index'] + 1):
            records_with_index.append({
                'index': index,
                'record': record
            })
        context['records_with_index'] = records_with_index
        
        return context

class ServiceRecordDeleteView(LoginRequiredMixin, UserPassesTestMixin, DeleteView):
    model = ServiceRecord
    success_url = reverse_lazy('service:service_records')
    
    def test_func(self):
        return self.request.user.user_type == 'service'
    
    def delete(self, request, *args, **kwargs):
        try:
            response = super().delete(request, *args, **kwargs)
            messages.success(request, 'ลบรายการเรียบร้อยแล้ว')
            return response
        except Exception as e:
            messages.error(request, f'เกิดข้อผิดพลาด: {str(e)}')
            return redirect('service:service_records')

# สร้างบันทึกงาน
class ServiceRecordCreateView(LoginRequiredMixin, UserPassesTestMixin, CreateView):
    model = ServiceRecord
    form_class = ServiceRecordForm
    template_name = 'service/record_form.html'
    success_url = reverse_lazy('service:service_records')

    def test_func(self):
        return self.request.user.user_type == 'service'

class ServiceRecordDetailView(LoginRequiredMixin, UserPassesTestMixin, DetailView):
    model = ServiceRecord
    template_name = 'service/record_detail.html'
    context_object_name = 'record'

    def test_func(self):
        # ตรวจสอบว่า user มี role เป็น 'service' หรือ 'ฝ่ายบริการ' หรือไม่
        return self.request.user.user_type == 'service'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        record = self.get_object()
        
        # เพิ่มข้อมูลสถานะการรับประกัน
        if record.warranty_expiry:
            today = timezone.now().date()
            context['warranty_status'] = 'ในประกัน' if record.warranty_expiry >= today else 'หมดประกัน'
            context['days_remaining'] = (record.warranty_expiry - today).days if record.warranty_expiry >= today else 0
        
        # เพิ่มข้อมูลการนัดหมาย
        if record.appointment_date:
            today = timezone.now().date()
            context['appointment_status'] = 'รอดำเนินการ' if record.appointment_date >= today else 'เลยกำหนด'
            context['days_to_appointment'] = (record.appointment_date - today).days
        
        # เพิ่มข้อมูลประวัติการบริการของลูกค้า
        context['service_history'] = ServiceRecord.objects.filter(
            customer=record.customer
        ).exclude(
            id=record.id
        ).order_by('-date', '-time')[:5]  # แสดง 5 รายการล่าสุด
        
        # เพิ่มข้อมูลสถิติ
        context['stats'] = {
            'total_services': ServiceRecord.objects.filter(customer=record.customer).count(),
            'completed_services': ServiceRecord.objects.filter(
                customer=record.customer,
                completion_status=True
            ).count(),
            'pending_services': ServiceRecord.objects.filter(
                customer=record.customer,
                completion_status=False
            ).count()
        }
        
        # เพิ่มข้อมูลโครงการ
        context['project_info'] = {
            'total_houses': ServiceRecord.objects.filter(project_name=record.project_name).count(),
            'total_services': ServiceRecord.objects.filter(
                project_name=record.project_name
            ).exclude(id=record.id).count()
        }
        
        # เพิ่มข้อมูลช่างเทคนิค
        if record.technician_name:
            context['technician_stats'] = {
                'total_services': ServiceRecord.objects.filter(
                    technician_name=record.technician_name
                ).count(),
                'completed_services': ServiceRecord.objects.filter(
                    technician_name=record.technician_name,
                    completion_status=True
                ).count()
            }
        
        # เพิ่มข้อมูลสำหรับการติดตาม
        context['timeline'] = [
            {
                'date': record.date,
                'event': 'รับแจ้งงาน',
                'details': record.description
            }
        ]
        if record.appointment_date:
            context['timeline'].append({
                'date': record.appointment_date,
                'event': 'นัดหมาย',
                'details': f'เวลา: {record.appointment_time}'
            })
        
        return context

class ServiceRecordUpdateView(LoginRequiredMixin, UserPassesTestMixin, UpdateView):
    model = ServiceRecord
    form_class = ServiceRecordForm
    template_name = 'service/record_form.html'
    
    def test_func(self):
        # ตรวจสอบว่า user มี role เป็น service หรือ ฝ่ายบริการ
        return self.request.user.user_type == 'service'

    def form_valid(self, form):
        try:
            # เก็บข้อมูลเดิม
            old_data = model_to_dict(self.get_object())
            
            # อัพเดทข้อมูลเพิ่มเติม
            self.object = form.save(commit=False)
            
            # อัพเดทเดือนและปีอัตโนมัติ
            if self.object.date:
                self.object.month = self.object.date.month
                self.object.year = str(self.object.date.year)
            
            # บันทึกข้อมูล
            self.object.save()
            
            # เก็บข้อมูลที่เปลี่ยนแปลง
            changed_fields = {}
            for field in form.changed_data:
                changed_fields[field] = {
                    'old': old_data.get(field),
                    'new': getattr(self.object, field)
                }
            
            # บันทึกประวัติ
            if changed_fields:
                ServiceRecordHistory.objects.create(
                    service_record=self.object,
                    modified_by=self.request.user,
                    modified_fields=changed_fields,
                    action='update',
                    description=f'แก้ไขโดย {self.request.user.get_full_name() or self.request.user.username}'
                )
                messages.success(self.request, 'บันทึกการแก้ไขเรียบร้อยแล้ว')
            
            return HttpResponseRedirect(self.get_success_url())
            
        except Exception as e:
            messages.error(self.request, f'เกิดข้อผิดพลาด: {str(e)}')
            return self.form_invalid(form)

    def get_success_url(self):
        return reverse_lazy('service:record_detail', kwargs={'pk': self.object.pk})

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['title'] = 'แก้ไขบันทึกการบริการ'
        return context

# ลบบันทึกงาน
class ServiceRecordDeleteView(LoginRequiredMixin, UserPassesTestMixin, DeleteView):
    model = ServiceRecord
    success_url = reverse_lazy('service:service_records')
    template_name = 'service/record_confirm_delete.html'
    
    def test_func(self):
        return self.request.user.user_type == 'service'
    
    def delete(self, request, *args, **kwargs):
        if not self.test_func():
            messages.error(self.request, 'คุณไม่มีสิทธิ์เข้าถึงหน้านี้')
            return HttpResponseRedirect(reverse_lazy('service:service_records'))
        messages.success(self.request, 'ลบข้อมูลเรียบร้อยแล้ว')
        return super().delete(request, *args, **kwargs)

# ปฏิทินของช่าง
class TechnicianCalendarView(LoginRequiredMixin, TechnicianRequired, TemplateView):
    template_name = 'service/technician_calendar.html'
    
    def get_status_colors(self):
        return {
            'assigned': {'bg': 'warning', 'color': '#ffc107'},
            'accepted': {'bg': 'info', 'color': '#17a2b8'},
            'traveling': {'bg': 'primary', 'color': '#007bff'},
            'arrived': {'bg': 'purple', 'color': '#6f42c1'},
            'fixing': {'bg': 'orange', 'color': '#fd7e14'},
            'completed': {'bg': 'success', 'color': '#28a745'},
            'cancelled': {'bg': 'danger', 'color': '#dc3545'},
            'rescheduled': {'bg': 'secondary', 'color': '#6c757d'}
        }
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        today = timezone.now().date()
        
        # ดึงงานวันนี้
        today_tasks = ServiceRequest.objects.filter(
            appointment_date=today,
            technician=self.request.user
        ).select_related('customer')
        
        # เพิ่ม status_color สำหรับ badge
        status_colors = self.get_status_colors()
        for task in today_tasks:
            task.status_color = status_colors.get(task.status, {}).get('bg', 'secondary')
        
        context['today_tasks'] = today_tasks
        return context

    class TechnicianCalendarView(LoginRequiredMixin, TechnicianRequired, TemplateView):
        template_name = 'service/technician_calendar.html'
        
        def get(self, request, *args, **kwargs):
            if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
                try:
                    events = []
                    appointments = ServiceRequest.objects.filter(
                        technician=self.request.user,
                        appointment_date__isnull=False
                    ).select_related('customer', 'customer__user')

                    status_colors = self.get_status_colors()

                    for appointment in appointments:
                        customer_info = appointment.get_customer_info()
                        event = {
                            'id': appointment.id,
                            'title': customer_info['customer_name'],
                            'start': appointment.appointment_date.isoformat(),
                            'backgroundColor': status_colors.get(appointment.status, {}).get('color', '#6c757d'),
                            'borderColor': status_colors.get(appointment.status, {}).get('color', '#6c757d'),
                            'extendedProps': {
                                'id': appointment.id,
                                'customer': customer_info['customer_name'],
                                'phone': customer_info['phone'],
                                'project_name': customer_info['project_name'],
                                'house_number': customer_info['house_number'],
                                'request_type': appointment.get_request_type_display(),
                                'status': appointment.status,
                                'status_display': appointment.get_status_display(),
                                'description': appointment.description,
                                'warranty_status': appointment.warranty_status,
                                'problem_topic': appointment.problem_topic,
                                'problem_description': appointment.problem_description or '',
                                'technician_username': appointment.technician.get_full_name() if appointment.technician else '',
                                'technician_display': appointment.technician.get_full_name() if appointment.technician else '',
                                'project_info': f"{customer_info['project_name']} - {customer_info['house_number']}"
                            }
                        }
                        
                        if appointment.appointment_time:
                            event['start'] = f"{appointment.appointment_date.isoformat()}T{appointment.appointment_time.strftime('%H:%M:%S')}"
                        
                        events.append(event)

                    return JsonResponse(events, safe=False)
                    
                except Exception as e:
                    return JsonResponse({'error': str(e)}, status=500)
                    
            return super().get(request, *args, **kwargs)

        def get_context_data(self, **kwargs):
            context = super().get_context_data(**kwargs)
            today = timezone.now().date()
            context['today_tasks'] = ServiceRequest.objects.filter(
                technician=self.request.user,
                appointment_date=today
            ).select_related('customer', 'customer__user')
            return context

class TechnicianDailySummaryView(LoginRequiredMixin, UserPassesTestMixin, TemplateView):
    template_name = 'service/technician_daily_summary.html'

    def get_status_color(self, status):
        status_colors = {
            'assigned': 'warning',
            'accepted': 'info',
            'traveling': 'primary',
            'arrived': 'purple',
            'fixing': 'orange',
            'completed': 'success',
        }
        return status_colors.get(status, 'secondary')

    def test_func(self):
        # อนุญาตให้ทั้งช่างและฝ่ายบริการเข้าถึงได้
        allowed_types = ['technician', 'service']
        return self.request.user.is_authenticated and self.request.user.user_type in allowed_types

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        
        # รับวันที่จาก URL parameter หรือใช้วันนี้
        date_str = self.request.GET.get('date')
        if date_str:
            selected_date = datetime.strptime(date_str, '%Y-%m-%d').date()
        else:
            selected_date = timezone.now().date()
            
        # กำหนดช่วงเวลา
        start_date = timezone.make_aware(datetime.combine(selected_date, datetime.min.time()))
        end_date = timezone.make_aware(datetime.combine(selected_date, datetime.max.time()))
        
        # ดึงงานตามประเภทผู้ใช้
        if self.request.user.user_type == 'technician':
            # ถ้าเป็นช่าง ดึงเฉพาะงานของตัวเอง
            daily_jobs = ServiceRequest.objects.filter(
                appointment_date__range=(start_date, end_date),
                technician=self.request.user
            )
        else:
            # ถ้าเป็นฝ่ายบริการ ดึงงานทั้งหมด
            daily_jobs = ServiceRequest.objects.filter(
                appointment_date__range=(start_date, end_date)
            )

        daily_jobs = daily_jobs.select_related('customer', 'technician').order_by('appointment_time')
        
        # ดึงงานที่เสร็จสิ้น
        completed_jobs = daily_jobs.filter(
            status__in=['completed']
        )
        
        # คำนวณสถิติ
        total_jobs = daily_jobs.count()
        completion_rate = (completed_jobs.count() / total_jobs * 100) if total_jobs > 0 else 0
        total_revenue = completed_jobs.aggregate(Sum('estimated_cost'))['estimated_cost__sum'] or 0
        
        # สรุปสถานะงาน
        job_summary = []
        status_choices = ServiceRequest.STATUS_CHOICES
        for status_code, status_display in status_choices:
            count = daily_jobs.filter(status=status_code).count()
            if count > 0:
                job_summary.append({
                    'status_display': status_display,
                    'status_color': self.get_status_color(status_code),
                    'count': count
                })

        # เพิ่มข้อมูลเพิ่มเติมสำหรับแต่ละงาน
        for job in daily_jobs:
            job.status_color = self.get_status_color(job.status)
            job.customer_name = job.customer.user.username if job.customer else "ไม่ระบุลูกค้า"
            job.formatted_time = job.appointment_time.strftime("%H:%M") if job.appointment_time else "ไม่ระบุเวลา"
            # แก้ไขตรงนี้ - เข้าถึง username โดยตรงจาก technician ซึ่งเป็น User object
            job.technician_name = job.technician.username if job.technician else "ยังไม่ได้กำหนดช่าง"

        # ไทม์ไลน์การอัพเดทสถานะ
        timeline_filter = {
            'service_request__appointment_date': selected_date  # เปลี่ยนเป็นใช้ appointment_date แทน
        }
        
        if self.request.user.user_type == 'technician':
            timeline_filter['service_request__technician'] = self.request.user

        job_timeline = TechnicianJobStatus.objects.filter(  # เปลี่ยนจาก TechnicianResponse เป็น TechnicianJobStatus
            **timeline_filter
        ).select_related(
            'service_request',
            'service_request__customer',
            'service_request__technician',
            'service_request__technician__customer'
        ).order_by('-created_at')

        context.update({
            'selected_date': selected_date,
            'prev_date': selected_date - timedelta(days=1),
            'next_date': selected_date + timedelta(days=1),
            'daily_jobs': daily_jobs,
            'total_jobs': total_jobs,
            'completion_rate': completion_rate,
            'total_revenue': total_revenue,
            'job_summary': job_summary,
            'job_timeline': job_timeline,
            'is_service': self.request.user.user_type == 'service',
        })
        return context

# ดูรายละเอียดงานของช่าง
class TechnicianTaskDetailView(LoginRequiredMixin, TechnicianRequired, BaseDetailView):
    model = ServiceRequest
    
    def render_to_response(self, context):
        task = self.object
        data = {
            'customer_name': task.customer.user.username,  # แก้ไขตรงนี้
            'request_type': task.get_request_type_display(),
            'status': task.get_status_display(),
            'created_at': task.created_at.strftime('%d/%m/%Y %H:%M'),
            'appointment_date': task.appointment_date.strftime('%d/%m/%Y') if task.appointment_date else None,
            'appointment_time': task.appointment_time.strftime('%H:%M') if task.appointment_time else None,
            'description': task.description
        }
        return JsonResponse(data)

@login_required
def submit_technician_advice(request, request_id):
    service_request = get_object_or_404(ServiceRequest, id=request_id)
    
    if request.method == 'POST' and request.user.user_type == 'technician' or request.user.user_type == 'service':
        advice = request.POST.get('advice')
        estimated_cost = request.POST.get('estimated_cost')
        
        if advice and estimated_cost:
            service_request.technician_advice = advice
            service_request.estimated_cost = estimated_cost
            service_request.status = 'advice_given'
            service_request.save()
            
            return JsonResponse({
                'status': 'success',
                'message': 'ส่งคำปรึกษาเรียบร้อยแล้ว'
            })
            
    return JsonResponse({
        'status': 'error',
        'message': 'ไม่สามารถส่งคำแนะนำได้'
    }, status=400)

@login_required
def confirm_customer_request(request, request_id):
    """สำหรับลูกค้ายืนยันหรือปฏิเสธคำแนะนำ"""
    if request.user.user_type != 'customer':
        return JsonResponse({
            'status': 'error',
            'message': 'ไม่มีสิทธิ์ดำเนินการ'
        }, status=403)

    service_request = get_object_or_404(ServiceRequest, id=request_id)
    
    if not hasattr(request.user, 'customer') or request.user.customer != service_request.customer:
        return JsonResponse({
            'status': 'error',
            'message': 'ไม่มีสิทธิ์ดำเนินการ'
        }, status=403)

    action = request.POST.get('action')
    if action not in ['confirm', 'reject']:
        return JsonResponse({
            'status': 'error',
            'message': 'Invalid action'
        }, status=400)

    try:
        if action == 'confirm':
            service_request.customer_confirmed = True
            service_request.status = 'accepted'
            message = 'ยืนยันการดำเนินการเรียบร้อย'
        else:
            service_request.status = 'cancelled'
            message = 'ปฏิเสธการดำเนินการเรียบร้อย'
            
        service_request.save()
        
        return JsonResponse({
            'status': 'success',
            'message': message
        })
    except Exception as e:
        return JsonResponse({
            'status': 'error',
            'message': str(e)
        }, status=500)

@login_required
def submit_service_recommendation(request, service_id):
    # ดึงข้อมูล ServiceRequest พร้อมข้อมูลที่เกี่ยวข้อง
    service_request = get_object_or_404(
        ServiceRequest.objects.select_related(
            'customer',
            'technician'
        ), 
        id=service_id
    )

    # ตรวจสอบสิทธิ์การเข้าถึง
    if not request.user.is_authenticated:
        messages.error(request, 'กรุณาเข้าสู่ระบบ')
        return redirect('login')

    # อนุญาตให้ทั้ง technician และ service เข้าถึงได้
    if request.user.user_type not in ['technician', 'service']:
        messages.error(request, 'ไม่มีสิทธิ์เข้าถึงหน้านี้')
        return redirect('service:request_list')

    # ถ้าเป็นช่าง ต้องตรวจสอบว่าเป็นช่างที่ได้รับมอบหมายงานนี้
    if request.user.user_type == 'technician':
        if service_request.technician != request.user:
            messages.error(request, 'คุณไม่ได้รับมอบหมายงานนี้')
            return redirect('service:request_list')

    if request.method == 'POST':
        try:
            # รับข้อมูลจากฟอร์ม
            description = request.POST.get('description')
            estimated_cost = request.POST.get('estimated_cost')
            service_type = request.POST.get('service_type')

            # ตรวจสอบข้อมูลที่จำเป็น
            if not all([description, service_type]):
                return JsonResponse({
                    'status': 'error',
                    'message': 'กรุณากรอกข้อมูลให้ครบถ้วน'
                }, status=400)

            # แปลงค่าใช้จ่ายเป็นตัวเลข
            try:
                estimated_cost = float(estimated_cost or 0)
            except ValueError:
                return JsonResponse({
                    'status': 'error',
                    'message': 'ราคาประเมินไม่ถูกต้อง'
                }, status=400)

            # สร้างข้อเสนอแนะ
            proposal = TechnicianProposal.objects.create(
                service_request=service_request,
                technician=request.user if request.user.user_type == 'technician' else service_request.technician,
                description=f"ประเภทงาน: {service_type}\n\nรายละเอียด: {description}",
                estimated_cost=estimated_cost
            )

            return JsonResponse({
                'status': 'success',
                'message': 'ส่งข้อเสนอแนะเรียบร้อยแล้ว'
            })

        except Exception as e:
            return JsonResponse({
                'status': 'error',
                'message': f'เกิดข้อผิดพลาด: {str(e)}'
            }, status=500)

    # สำหรับ GET request
    context = {
        'service_request': service_request,
        'customer': service_request.customer,
    }
    return render(request, 'service/service_recommendation.html', context)

# ดูปฏิทินของช่าง
@login_required
def get_technician_events(request):
    try:
        # ตรวจสอบสิทธิ์การเข้าถึง
        if request.user.user_type not in ['technician', 'service']:
            return JsonResponse({'error': 'Permission denied'}, status=403)

        # ตรวจสอบพารามิเตอร์วันที่
        start = request.GET.get('start')
        end = request.GET.get('end')
        specific_date = request.GET.get('date')  # เพิ่มการรับค่าวันที่เฉพาะ

        # กำหนดค่าสีสถานะ
        status_colors = {
            'assigned': '#ffc107',
            'accepted': '#17a2b8',
            'traveling': '#007bff',
            'arrived': '#6f42c1',
            'fixing': '#fd7e14',
            'completed': '#28a745',
            'cancelled': '#dc3545',
            'rescheduled': '#6c757d'
        }

        # สร้าง query พื้นฐาน
        events_query = ServiceRequest.objects.select_related('customer', 'technician')

        # กรองตามช่างถ้าผู้ใช้เป็นช่าง
        if request.user.user_type == 'technician':
            events_query = events_query.filter(technician=request.user)

        # กรองตามวันที่
        if specific_date:
            try:
                selected_date = datetime.strptime(specific_date, '%Y-%m-%d').date()
                events_query = events_query.filter(appointment_date=selected_date)
            except ValueError:
                return JsonResponse({'error': 'Invalid date format'}, status=400)
        elif start and end:
            try:
                start_date = start.split('T')[0]
                end_date = end.split('T')[0]
                events_query = events_query.filter(
                    appointment_date__range=[start_date, end_date]
                )
            except (ValueError, AttributeError) as e:
                print(f"Date parsing error: {str(e)}")
                return JsonResponse([], safe=False)

        # แปลงข้อมูลเป็น format สำหรับ FullCalendar
        calendar_events = []
        for event in events_query:
            try:
                if event.appointment_date:
                    event_time = event.appointment_time or timezone.now().time()
                    start_datetime = datetime.combine(event.appointment_date, event_time)
                    
                    # สร้างข้อมูลที่จะแสดง
                    project_info = f"{event.customer.project_name} {event.customer.house_number}"
                    customer_name = event.customer.user.get_full_name() or event.customer.user.username
                    technician_info = f"{event.technician.get_full_name() or event.technician.username}"

                    event_data = {
                        'id': str(event.id),
                        'title': customer_name,  # แสดงชื่อลูกค้าเป็นชื่องาน
                        'start': start_datetime.isoformat(),
                        'status': event.status,
                        'backgroundColor': status_colors.get(event.status, '#6c757d'),
                        'borderColor': status_colors.get(event.status, '#6c757d'),
                        'extendedProps': {
                            'customer': customer_name,
                            'project_name': event.customer.project_name,
                            'house_number': event.customer.house_number,
                            'project_info': project_info,
                            'phone': event.customer.phone,
                            'appointment_time': event.appointment_time.strftime('%H:%M') if event.appointment_time else '',
                            'description': event.description or '',
                            'status': event.status,
                            'status_display': event.get_status_display(),
                            'request_type': event.get_request_type_display(),
                            'technician_info': technician_info,
                            'warranty_status': event.get_warranty_status_display(),
                        }
                    }
                    calendar_events.append(event_data)
            except Exception as e:
                print(f"เกิดข้อผิดพลาดในการประมวลผลงาน {event.id}: {str(e)}")
                continue

        return JsonResponse(calendar_events, safe=False)

    except Exception as e:
        print(f"เกิดข้อผิดพลาดใน get_technician_events: {str(e)}")
        return JsonResponse({'error': str(e)}, status=500)


@login_required
def accept_request(request, pk):
    if request.method == 'POST' and request.user.user_type == 'technician':
        service_request = get_object_or_404(ServiceRequest, pk=pk)
        
        if service_request.technician == request.user:
            service_request.status = 'pending_advice'
            service_request.save()
            
            TechnicianJobStatus.objects.create(
                service_request=service_request,
                technician=request.user,
                status='accepted',
                notes='ช่างรับงานและเตรียมให้คำแนะนำ'
            )
            
            messages.success(request, 'รับงานเรียบร้อยแล้ว กรุณาให้คำแนะนำแก่ลูกค้า')
            
    return redirect('service:request_detail', pk=pk)

@login_required
def confirm_advice(request, pk):
    if request.method == 'POST':
        service_request = get_object_or_404(ServiceRequest, pk=pk)
        
        if request.user == service_request.customer:
            service_request.status = 'assigned'
            service_request.save()
            
            TechnicianJobStatus.objects.create(
                service_request=service_request,
                technician=service_request.technician,
                status='assigned',
                notes='ลูกค้ายืนยันคำแนะนำและพร้อมดำเนินการ'
            )
            
            messages.success(request, 'ยืนยันคำแนะนำเรียบร้อยแล้ว ช่างจะดำเนินการในขั้นตอนต่อไป')
            
    return redirect('service:request_detail', pk=pk)

# อนุญาติการตอบรับของลูกค้า
@login_required
def approve_proposal(request, proposal_id):
    proposal = get_object_or_404(TechnicianProposal, id=proposal_id)
    if request.method == 'POST' and request.user.user_type == 'customer':
        proposal.is_approved = True
        proposal.save()
        proposal.service_request.status = 'customer_approved'
        proposal.service_request.save()
        return redirect('service:request_detail', pk=proposal.service_request.pk)
    return redirect('service:request_list')

# ส่งข้อเสนอแนะการซ่อม
@login_required
def submit_service_recommendation(request, service_id):
    # ตรวจสอบว่าเป็นช่างหรือไม่
    if request.user.user_type != 'technician' and request.user.user_type != 'service':
        return HttpResponseForbidden("ไม่มีสิทธิ์เข้าถึง")
        
    service_request = get_object_or_404(ServiceRequest, id=service_id)
    
    if request.method == 'POST':
        try:
            # รับข้อมูลจากฟอร์ม
            service_type = request.POST.get('service_type')
            description = request.POST.get('description')
            estimated_cost = request.POST.get('estimated_cost')
            
            # บันทึกคำแนะนำ
            service_request.technician_advice = description
            service_request.estimated_cost = estimated_cost
            service_request.save()
            
            return JsonResponse({
                'status': 'success',
                'message': 'บันทึกคำแนะนำเรียบร้อยแล้ว'
            })
        except Exception as e:
            return JsonResponse({
                'status': 'error',
                'message': str(e)
            }, status=400)
    else:
        # แสดงหน้าฟอร์มให้คำแนะนำ
        context = {
            'service_request': service_request,
            'customer': service_request.customer
        }
        return render(request, 'service/service_recommendation.html', context)

# อัพเดทสถานะงานของช่าง
@login_required
def update_job_status(request, service_id):
    if request.method == 'POST' and request.user.user_type == 'technician' and request.user.user_type == 'service':
        service_request = get_object_or_404(ServiceRequest, id=service_id)
        status = TechnicianJobStatus.objects.create(
            service_request=service_request,
            technician=request.user,
            service=request.user,
            status=request.POST.get('status')
        )
        
        if 'photos' in request.FILES:
            for photo in request.FILES.getlist('photos'):
                try:
                    # สร้าง ServiceImage object แต่ยังไม่บันทึก
                    image = ServiceImage(
                        service_request=service_request,
                        image=photo,
                        description=request.POST.get('image_description', '')
                    )
                    
                    # ตรวจสอบรูปซ้ำด้วย hash
                    image_hash = image.generate_hash()
                    if not ServiceImage.objects.filter(
                        service_request=service_request,
                        image_hash=image_hash
                    ).exists():
                        image.save()  # บันทึกเฉพาะรูปที่ไม่ซ้ำ
                    
                except ValidationError as e:
                    return JsonResponse({
                        'status': 'error',
                        'message': str(e)
                    }, status=400)
        
        if status.status in ['completed_cash', 'completed_call']:
            service_request.status = 'completed'
            service_request.save()
            
        return JsonResponse({'status': 'success'})
    return JsonResponse({'status': 'error'}, status=403)

@login_required
def update_service_status(request, request_id):
    if request.method == 'POST':
        try:
            service_request = get_object_or_404(ServiceRequest, id=request_id)
            new_status = request.POST.get('status')
            
            # ตรวจสอบว่ามี status ส่งมาหรือไม่
            if not new_status:
                return JsonResponse({
                    'status': 'error',
                    'message': 'ไม่พบข้อมูลสถานะ'
                }, status=400)

            # ตรวจสอบสิทธิ์
            if not (request.user.user_type == 'technician' and service_request.technician == request.user) and \
               not (request.user.user_type == 'service'):
                return JsonResponse({
                    'status': 'error',
                    'message': 'ไม่มีสิทธิ์ในการอัพเดทสถานะ'
                }, status=403)

            # อัพเดทสถานะ
            service_request.status = new_status
            service_request.save()

            # บันทึกประวัติ
            TechnicianJobStatus.objects.create(
                service_request=service_request,
                technician=request.user if request.user.user_type == 'technician' else None,
                status=new_status,
                notes=request.POST.get('notes', '')
            )

            # จัดการรูปภาพ
            if request.FILES.getlist('photos'):
                photos = request.FILES.getlist('photos')
                if len(photos) > 6:
                    return JsonResponse({
                        'status': 'error',
                        'message': 'อัพโหลดได้สูงสุด 6 รูป'
                    }, status=400)

                for photo in photos:
                    ServiceImage.objects.create(
                        service_request=service_request,
                        image=photo,
                        description=request.POST.get('image_description', ''),
                        uploaded_by=request.user
                    )

            return JsonResponse({
                'status': 'success',
                'message': 'อัพเดทสถานะเรียบร้อย'
            })

        except Exception as e:
            return JsonResponse({
                'status': 'error',
                'message': str(e)
            }, status=500)

    return JsonResponse({
        'status': 'error',
        'message': 'Method not allowed'
    }, status=405)

@login_required
@require_POST
def update_service_advice(request, request_id):
    if request.user.user_type != 'service':
        return JsonResponse({
            'status': 'error',
            'message': 'ไม่มีสิทธิ์ดำเนินการ'
        }, status=403)

    try:
        import json
        data = json.loads(request.body)
        service_request = ServiceRequest.objects.get(id=request_id)
        
        service_request.technician_advice = data.get('advice')
        service_request.estimated_cost = Decimal(data.get('estimated_cost', '0'))
        service_request.advice_updated_by = request.user
        service_request.advice_updated_at = timezone.now()
        service_request.save()

        return JsonResponse({
            'status': 'success',
            'message': 'บันทึกคำแนะนำเรียบร้อย'
        })

    except ServiceRequest.DoesNotExist:
        return JsonResponse({
            'status': 'error',
            'message': 'ไม่พบข้อมูลการแจ้งซ่อม'
        }, status=404)
    except Exception as e:
        return JsonResponse({
            'status': 'error',
            'message': str(e)
        }, status=400)

# ยืนยันการแจ้งซ่อม
@login_required
def confirm_service_request(request, request_id):
    """สำหรับฝ่ายบริการยืนยันการแจ้งซ่อม"""
    if request.user.user_type != 'service':
        return JsonResponse({
            'status': 'error',
            'message': 'ไม่มีสิทธิ์ดำเนินการ'
        }, status=403)

    service_request = get_object_or_404(ServiceRequest, id=request_id)
    
    try:
        service_request.is_confirmed = True
        service_request.status = 'confirmed'
        service_request.save()
        
        return JsonResponse({
            'status': 'success',
            'message': 'ยืนยันการแจ้งซ่อมเรียบร้อย'
        })
    except Exception as e:
        return JsonResponse({
            'status': 'error',
            'message': str(e)
        }, status=500)

@login_required
def manage_warranty(request, pk):
    """จัดการประกันสินค้า"""
    if request.user.user_type != 'service':
        return JsonResponse({
            'status': 'error',
            'message': 'ไม่มีสิทธิ์ดำเนินการ'
        }, status=403)

    service_request = get_object_or_404(ServiceRequest, pk=pk)
    
    if request.method == 'POST':
        action = request.POST.get('action')
        warranty_date = request.POST.get('warranty_date')
        
        try:
            if action == 'set_warranty':
                # แปลงวันที่จาก string เป็น date object
                start_date = datetime.strptime(warranty_date, '%Y-%m-%d').date() if warranty_date else None
                
                # อัพเดทข้อมูลประกันของลูกค้า
                customer = service_request.customer
                customer.warranty_status = 'ACTIVE'
                customer.warranty_expiry_date = start_date + timedelta(days=365) if start_date else None
                customer.save()
                
                # อัพเดทข้อมูลประกันของ service request
                service_request.set_warranty(start_date)
                
                return JsonResponse({
                    'status': 'success',
                    'message': 'ตั้งค่าประกันเรียบร้อยแล้ว',
                    'warranty_start': service_request.warranty_start_date.strftime('%d/%m/%Y'),
                    'warranty_end': service_request.warranty_end_date.strftime('%d/%m/%Y')
                })
            
            elif action == 'remove_warranty':
                # อัพเดทข้อมูลประกันของลูกค้า
                customer = service_request.customer
                customer.warranty_status = 'NONE'
                customer.warranty_expiry_date = None
                customer.save()
                
                # อัพเดทข้อมูลประกันของ service request
                service_request.warranty_status = 'out_of_warranty'
                service_request.warranty_start_date = None
                service_request.warranty_end_date = None
                service_request.save()
                
                return JsonResponse({
                    'status': 'success',
                    'message': 'ยกเลิกประกันเรียบร้อยแล้ว'
                })
                
        except Exception as e:
            return JsonResponse({
                'status': 'error',
                'message': str(e)
            }, status=400)
            
    return JsonResponse({
        'status': 'error',
        'message': 'Method not allowed'
    }, status=405)

# ลบรูปภาพงาน
@login_required
def delete_service_image(request, image_id):
    if request.method == 'POST':
        try:
            image = ServiceImage.objects.get(id=image_id)
            
            # ตรวจสอบสิทธิ์
            if request.user.user_type != 'technician' and request.user.user_type != 'service':
                return JsonResponse({
                    'status': 'error',
                    'message': 'ไม่มีสิทธิ์ลบรูปภาพนี้'
                }, status=403)
            
            # ลบไฟล์รูปภาพ
            if image.image:
                if os.path.isfile(image.image.path):
                    os.remove(image.image.path)
            
            # ลบข้อมูลในฐานข้อมูล
            image.delete()
            
            return JsonResponse({'status': 'success'})
            
        except ServiceImage.DoesNotExist:
            return JsonResponse({
                'status': 'error',
                'message': 'ไม่พบรูปภาพ'
            }, status=404)
        except Exception as e:
            return JsonResponse({
                'status': 'error',
                'message': str(e)
            }, status=500)
    
    return JsonResponse({
        'status': 'error',
        'message': 'Method not allowed'
    }, status=405)

# สร้างใบกำกับภาษี
@login_required
def generate_bill(request, service_id):
    if request.user.user_type != 'service':
        return JsonResponse({'status': 'error', 'message': 'Permission denied'}, status=403)
        
    service_request = get_object_or_404(ServiceRequest, id=service_id)
    bill_data = {
        'customer_name': service_request.customer.user.username,  # แก้ไขตรงนี้
        'project_name': service_request.customer.project_name,
        'service_date': service_request.created_at,
        'service_details': service_request.description,
        'amount': service_request.technician_response.estimated_cost if hasattr(service_request, 'technician_response') else 0,
    }
    
    return JsonResponse({
        'status': 'success',
        'bill_data': bill_data
    })

# ตรวจสอบสิทธิ์การเข้าถึงข้อมูล
class StaffRequired(UserPassesTestMixin):
    def test_func(self):
        return self.request.user.user_type in ['service', 'technician']

# ดูรายการงานของฝ่ายบริการ
class ServiceRequestManageView(LoginRequiredMixin, StaffRequired, ListView):
    model = ServiceRequest
    template_name = 'service/service_request_manage.html'
    context_object_name = 'service_requests'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        
        # เพิ่ม status_colors dictionary
        context['status_colors'] = {
            'assigned': 'warning',
            'accepted': 'info',
            'traveling': 'primary',
            'arrived': 'purple',
            'fixing': 'orange',
            'completed': 'success',
            'cancelled': 'danger',
            'rescheduled': 'secondary'
        }
        return context

    def get_queryset(self):
        queryset = ServiceRequest.objects.select_related(
            'customer', 
            'technician', 
        )
        
        if self.request.user.user_type == 'technician':
            # ช่างจะเห็นเฉพาะงานที่ได้รับมอบหมาย
            return queryset.filter(technician=self.request.user)
        
        # ฝ่ายบริการเห็นทุกงาน
        return queryset.all()

# ส่งออกข้อมูลงาน excel สำหรับฝ่ายบริการ
@login_required
def export_service_requests(request):
    """ส่งออกข้อมูลการแจ้งซ่อมเป็นไฟล์ Excel"""
    if request.user.user_type not in ['service', 'technician']:
        return HttpResponseForbidden("ไม่มีสิทธิ์เข้าถึง")

    # สร้าง Workbook ใหม่
    wb = Workbook()
    ws = wb.active
    ws.title = "Service Requests"

    # กำหนดหัวคอลัมน์
    headers = [
        'เลขที่คำขอ',
        'วันที่แจ้ง',
        'วันที่นัดหมาย',
        'เวลานัดหมาย',
        'ลูกค้า',
        'โครงการ',
        'บ้านเลขที่',
        'เบอร์โทร',
        'ประเภทงาน',
        'รายละเอียด',
        'ช่างผู้รับผิดชอบ',
        'สถานะ',
        'สถานะประกัน',
        'ค่าใช้จ่าย',
        'หมายเหตุค่าใช้จ่าย'
    ]
    ws.append(headers)

    # ดึงข้อมูลตามสิทธิ์การเข้าถึง
    if request.user.user_type == 'technician':
        queryset = ServiceRequest.objects.filter(technician=request.user).order_by('id')
    else:
        queryset = ServiceRequest.objects.all().order_by('id')

    # เพิ่มข้อมูลลงในไฟล์ Excel
    for service_request in queryset.select_related('customer', 'technician'):
        row = [
            service_request.id,
            service_request.created_at.strftime('%d/%m/%Y'),
            service_request.appointment_date.strftime('%d/%m/%Y') if service_request.appointment_date else '',
            service_request.appointment_time.strftime('%H:%M') if service_request.appointment_time else '',
            service_request.customer.user.username,  # แก้ไขตรงนี้
            service_request.customer.project_name,
            service_request.customer.house_number,
            service_request.customer.phone,
            service_request.get_request_type_display(),
            service_request.description,
            service_request.technician.customer.customer_name if service_request.technician else '',  # แก้ไขตรงนี้
            service_request.get_status_display(),
            service_request.get_warranty_status_display(),
            str(service_request.estimated_cost) if service_request.estimated_cost else '0',
            service_request.cost_note or ''
        ]
        ws.append(row)

    # ปรับความกว้างคอลัมน์อัตโนมัติ
    for column in ws.columns:
        max_length = 0
        column_letter = column[0].column_letter
        for cell in column:
            try:
                if len(str(cell.value)) > max_length:
                    max_length = len(str(cell.value))
            except:
                pass
        adjusted_width = (max_length + 2)
        ws.column_dimensions[column_letter].width = adjusted_width

    # สร้าง response
    response = HttpResponse(
        content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
    )
    response['Content-Disposition'] = 'attachment; filename=service_requests.xlsx'

    # บันทึกไฟล์
    wb.save(response)
    return response


# อัพเดทสถานะงานของฝ่ายบริการ
class UpdateServiceStatusView(LoginRequiredMixin, StaffRequired, UpdateView):
    model = ServiceRequest
    template_name = 'service/update_service_status.html'
    fields = ['status', 'technician']
    success_url = reverse_lazy('service:manage_requests')

    def get_form(self, form_class=None):
        form = super().get_form(form_class)
        
        # เลือกตัวเลือกสถานะตามประเภทผู้ใช้
        if self.request.user.user_type == 'technician':
            # ช่างจะเห็นเฉพาะสถานะที่กำหนดใน TechnicianJobStatus
            form.fields['status'].choices = TechnicianJobStatus.TECHNICIAN_STATUS_CHOICES
        else:
            # ฝ่ายบริการจะเห็นสถานะทั้งหมดจาก ServiceRequest
            form.fields['status'].choices = ServiceRequest.STATUS_CHOICES
        
        return form

    def form_valid(self, form):
        new_status = form.cleaned_data['status']
        
        # ตรวจสอบสถานะตามประเภทผู้ใช้
        if self.request.user.user_type == 'technician':
            valid_statuses = dict(TechnicianJobStatus.TECHNICIAN_STATUS_CHOICES)
            if new_status not in valid_statuses:
                messages.error(self.request, 'สถานะที่เลือกไม่ถูกต้องสำหรับช่าง')
                return self.form_invalid(form)
        else:
            valid_statuses = dict(ServiceRequest.STATUS_CHOICES)
            if new_status not in valid_statuses:
                messages.error(self.request, 'สถานะที่เลือกไม่ถูกต้อง')
                return self.form_invalid(form)

        response = super().form_valid(form)
        
        # บันทึกประวัติการอัพเดทสถานะ
        TechnicianJobStatus.objects.create(
            service_request=self.object,
            technician=self.request.user,
            status=new_status,
            notes=self.request.POST.get('notes', '')
        )
        
        messages.success(self.request, 'อัพเดทสถานะเรียบร้อยแล้ว')
        return response

class CustomerMapView(LoginRequiredMixin, UserPassesTestMixin, TemplateView):
    template_name = 'service/customer_map.html'
    
    def test_func(self):
        return self.request.user.user_type in ['service', 'technician']
        
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        # ดึงข้อมูลลูกค้าที่มีพิกัด
        customers = Customer.objects.filter(
            latitude__isnull=False,
            longitude__isnull=False
        ).select_related('user')
        
        # สร้าง markers สำหรับแสดงบนแผนที่
        markers = []
        for customer in customers:
            markers.append({
                'lat': float(customer.latitude),
                'lng': float(customer.longitude),
                'name': customer.user.username,
                'project': customer.project_name,
                'house_number': customer.house_number,
                'location': customer.location,
                'phone': customer.phone
            })
            
        context['markers'] = markers
        return context

@require_POST
def upload_excel(request):
    if request.user.user_type != 'service':
        return JsonResponse({
            'status': 'error',
            'message': 'ไม่มีสิทธิ์ในการนำเข้าข้อมูล'
        }, status=403)
        
    try:
        excel_file = request.FILES['excel_file']
        df = pd.read_excel(excel_file)
        
        # สร้าง default user สำหรับ import data
        default_user, created = User.objects.get_or_create(
            username='default_user',
            defaults={
                'email': 'imported@example.com',
                'first_name': 'Imported',
                'last_name': 'Records',
                'is_active': False,
                'user_type': 'customer'
            }
        )

        # สร้าง default customer สำหรับ import data
        default_customer, created = Customer.objects.get_or_create(
            user=default_user,
            defaults={
                'problem_type': 'OTHER',
                'warranty_status': 'NONE'
            }
        )

        service_requests_created = 0
        success_count = 0
        error_records = []
        duplicate_records = []
        linked_records = 0

        for index, row in df.iterrows():
            try:
                # แปลงวันที่
                date_obj = None
                try:
                    date_str = str(row['วดป.'])
                    if '/' in date_str:
                        day, month, year = date_str.split('/')
                        year = int(year) - 543
                        date_str = f"{year}-{month.zfill(2)}-{day.zfill(2)}"
                    date_obj = pd.to_datetime(date_str).date()
                except Exception as e:
                    print(f"Error parsing date: {date_str}")

                # แปลงเวลา
                time_obj = None
                try:
                    time_str = str(row['เวลา'])
                    if pd.notna(time_str) and time_str != '-':
                        time_str = time_str.replace(' น.', '').replace('น.', '')
                        if '.' in time_str:
                            hour, minute = time_str.split('.')
                            time_str = f"{hour.zfill(2)}:{minute.zfill(2)}"
                        time_obj = datetime.strptime(time_str, '%H:%M').time()
                except Exception as e:
                    print(f"Error parsing time: {row['เวลา']}")

                # ค้นหาลูกค้าที่มีข้อมูลตรงกัน
                matching_customer = None
                if pd.notna(row['โครงการ']) and pd.notna(row['บ้านเลขที่']):
                    matching_customer = Customer.objects.filter(
                        project_name=str(row['โครงการ'])[:100],
                        house_number=str(row['บ้านเลขที่'])[:50]
                    ).first()

                customer = matching_customer if matching_customer else default_customer

                # ตรวจสอบข้อมูลซ้ำ
                job_number = str(row['เลขงาน'])[:50] if pd.notna(row['เลขงาน']) else ''
                existing_record = ServiceRecord.objects.filter(
                    job_number=job_number,
                    date=date_obj
                ).first()

                if existing_record:
                    duplicate_records.append({
                        'row': index + 2,
                        'job_number': job_number,
                        'customer_name': str(row['ชื่อลูกบ้าน'])[:100] if pd.notna(row['ชื่อลูกบ้าน']) else '',
                        'date': date_obj.strftime('%Y-%m-%d') if date_obj else None
                    })
                    service_record = existing_record
                else:
                    # กำหนดสถานะและ completion_status
                    status = 'completed' if str(row['สถานะ']) in ['จบงาน', 'จบงาน/ให้คำปรึกษา'] else 'pending'
                    completion_status = True if status == 'completed' or str(row['สถานะจบงาน']) in ['√', ' '] else False

                    # สร้าง ServiceRecord
                    service_record = ServiceRecord.objects.create(
                        sequence=int(row['ลำดับ']) if pd.notna(row['ลำดับ']) else 0,
                        completion_status=completion_status,
                        year=str(row['ปี พ.ศ.'])[:4] if pd.notna(row['ปี พ.ศ.']) else '',
                        date=date_obj,
                        month=int(row['ด.']) if pd.notna(row['ด.']) else None,
                        time=time_obj,
                        job_number=job_number,
                        customer=customer,
                        customer_name=str(row['ชื่อลูกบ้าน'])[:100] if pd.notna(row['ชื่อลูกบ้าน']) else '',
                        customer_phone=str(row['เบอร์ติดต่อ'])[:15] if pd.notna(row['เบอร์ติดต่อ']) else '',
                        technician_name=str(row['จนท.'])[:100] if pd.notna(row['จนท.']) else '',
                        technician_phone=str(row['เบอร์ติดต่อ จนท.'])[:15] if pd.notna(row['เบอร์ติดต่อ จนท.']) else '',
                        project_code=str(row['รหัสโครงการ'])[:50] if pd.notna(row['รหัสโครงการ']) else '',
                        project_name=str(row['โครงการ'])[:100] if pd.notna(row['โครงการ']) else '',
                        house_number=str(row['บ้านเลขที่'])[:50] if pd.notna(row['บ้านเลขที่']) else '',
                        plot_number=str(row['แปลง'])[:50] if pd.notna(row['แปลง']) else '',
                        house_type=str(row['แบบ'])[:50] if pd.notna(row['แบบ']) else '',
                        description=str(row['อาการรับแจ้ง']) if pd.notna(row['อาการรับแจ้ง']) else '',
                        status=status,
                        equipment_status=str(row['วัสดุ/อุปกรณ์ที่ผิดปกติ']) if pd.notna(row['วัสดุ/อุปกรณ์ที่ผิดปกติ']) else '',
                        cause_found=str(row['สาเหตุที่ตรวจพบ']) if pd.notna(row['สาเหตุที่ตรวจพบ']) else '',
                        solution=str(row['การแก้ไข']) if pd.notna(row['การแก้ไข']) else '',
                        notes=str(row['หมายเหตุ']) if pd.notna(row['หมายเหตุ']) else ''
                    )
                    success_count += 1

                # สร้าง ServiceRequest หลังจากสร้าง ServiceRecord
                if matching_customer and pd.notna(row['อาการรับแจ้ง']):
                    linked_records += 1
                    description = str(row['อาการรับแจ้ง'])
                    
                    # ตรวจสอบว่ามี ServiceRequest อยู่แล้วหรือไม่
                    existing_request = ServiceRequest.objects.filter(
                        Q(customer=matching_customer) &
                        (
                            Q(service_record__job_number=job_number) |
                            (
                                Q(created_at__date=date_obj) &
                                Q(description=description) &
                                Q(customer__project_name=str(row['โครงการ'])[:100]) &
                                Q(customer__house_number=str(row['บ้านเลขที่'])[:50])
                            )
                        )
                    ).exists()
                    
                    if not existing_request:
                        warranty_status = 'in_warranty' if pd.notna(row['วันที่หมดประกัน']) else 'out_of_warranty'
                        status = 'completed' if str(row['สถานะ']) in ['จบงาน', 'จบงาน/ให้คำปรึกษา'] else 'pending'
                        
                        service_request = ServiceRequest.objects.create(
                            customer=matching_customer,
                            request_type='repair',
                            description=description,
                            status=status,
                            appointment_date=date_obj,
                            appointment_time=time_obj,
                            need_advice=True,
                            warranty_status=warranty_status,
                            service_record=service_record,
                            created_at=datetime.combine(date_obj, time_obj) if time_obj else datetime.combine(date_obj, datetime.min.time())
                        )
                        
                        # อัพเดทสถานะใน ServiceRecord
                        service_record.update_status_from_request()
                        service_requests_created += 1

            except Exception as e:
                error_records.append({
                    'row': index + 2,
                    'error': str(e)
                })
                continue

        response_data = {
            'status': 'success',
            'message': (
                f'นำเข้าข้อมูลสำเร็จ {success_count} รายการ\n'
                f'เชื่อมโยงกับลูกค้า {linked_records} รายการ\n'
                f'สร้างรายการแจ้งซ่อมอัตโนมัติ {service_requests_created} รายการ'
            ),
            'errors': error_records if error_records else None,
        }

        if duplicate_records:
            response_data['duplicates'] = duplicate_records
            response_data['message'] += f'\nพบข้อมูลซ้ำ {len(duplicate_records)} รายการ'

        return JsonResponse(response_data)

    except Exception as e:
        return JsonResponse({
            'status': 'error',
            'message': f'เกิดข้อผิดพลาด: {str(e)}'
        }, status=400)

def download_template(request):
    wb = Workbook()
    ws = wb.active
    ws.title = "Template"
    
    # กำหนดหัวคอลัมน์
    headers = [
        'ลำดับ', 'สถานะจบงาน', 'ปี พ.ศ.', 'วดป.', 'ด.', 'เวลา', 
        'เลขงาน', 'เลขที่บิล', 'ชื่อลูกบ้าน', 'เบอร์ติดต่อ', 'จนท.', 
        'เบอร์ติดต่อ จนท.', 'รหัสโครงการ', 'โครงการ', 'บ้านเลขที่', 
        'แปลง', 'แบบ', 'โอน', 'วันที่หมดประกัน', 'อาการรับแจ้ง', 
        'สถานะ', 'วันนัด', 'เวลานัด', 'วัสดุ/อุปกรณ์ที่ผิดปกติ', 
        'สาเหตุที่ตรวจพบ', 'การแก้ไข', 'ชื่อ', 'หมายเหตุ', 'จำนวน', 
        'Link รูปภาพที่ออกSERVICE', 'หมายเหตุเพิ่มเติม'
    ]
    ws.append(headers)
    
    # ตัวอย่างข้อมูล
    sample_data = [
        1, 'เสร็จ', '2566', '2566-01-01', 1, '09:00',
        'AF66-0001', 'BILL001', 'คุณลูกค้า', '0812345678', 'ช่างA',
        '0898765432', 'CSN', 'โครงการA', '123/45', 
        'A-01', 'Type-A', '2565-01-01', '2567-01-01', 'เครื่องปรับอากาศไม่เย็น',
        'รอดำเนินการ', '2566-01-02', '10:00', 'คอยล์เย็นสกปรก',
        'ฝุ่นอุดตัน', 'ล้างทำความสะอาด', 'ช่างA,ช่างB', 'งานเสร็จเรียบร้อย', 1500,
        'http://example.com/image1.jpg', 'ลูกค้าพอใจมาก'
    ]
    ws.append(sample_data)

    # ปรับความกว้างคอลัมน์
    for col in ws.columns:
        max_length = 0
        column = col[0].column_letter
        for cell in col:
            try:
                if len(str(cell.value)) > max_length:
                    max_length = len(str(cell.value))
            except:
                pass
        adjusted_width = (max_length + 2)
        ws.column_dimensions[column].width = adjusted_width

    # สร้าง response
    buffer = io.BytesIO()
    wb.save(buffer)
    buffer.seek(0)

    response = HttpResponse(
        buffer.read(),
        content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
    )
    response['Content-Disposition'] = 'attachment; filename=service_record_template.xlsx'
    return response

# เพิ่มเมธอดใหม่สำหรับจัดการการคำนวณราคา
def calculate_service_fee(request, service_id):
    if request.user.user_type != 'service':
        return JsonResponse({'status': 'error', 'message': 'Permission denied'}, status=403)
    
    service_request = get_object_or_404(ServiceRequest, id=service_id)
    
    try:
        # เรียกใช้เมธอด calculate_service_fee จาก model
        fee = service_request.calculate_service_fee()
        
        return JsonResponse({
            'status': 'success',
            'fee': str(fee)
        })
    except Exception as e:
        return JsonResponse({
            'status': 'error',
            'message': str(e)
        }, status=500)

# แก้ไขเมธอด set_service_cost เดิม
@login_required
@require_POST
def set_service_cost(request, request_id):
    if request.user.user_type != 'service':
        return JsonResponse({
            'status': 'error',
            'message': 'ไม่มีสิทธิ์ดำเนินการ'
        }, status=403)

    try:
        service_request = ServiceRequest.objects.get(id=request_id)
        
        # ตรวจสอบสถานะประกันก่อนกำหนดค่าใช้จ่าย
        service_request.check_warranty_status()
        
        if service_request.warranty_status == 'in_warranty':
            estimated_cost = Decimal('0.00')
            cost_note = 'งานอยู่ในประกัน'
        else:
            estimated_cost = Decimal(request.POST.get('estimated_cost', '0'))
            cost_note = request.POST.get('cost_note', '')

        if estimated_cost < 0:
            raise ValueError('ค่าใช้จ่ายต้องไม่ติดลบ')

        service_request.estimated_cost = estimated_cost
        service_request.cost_note = cost_note
        service_request.cost_updated_by = request.user
        service_request.cost_updated_at = timezone.now()
        service_request.save()

        return JsonResponse({
            'status': 'success',
            'message': 'บันทึกค่าใช้จ่ายเรียบร้อย',
            'estimated_cost': str(estimated_cost),
            'warranty_status': service_request.warranty_status
        })

    except (ServiceRequest.DoesNotExist, ValueError) as e:
        return JsonResponse({
            'status': 'error',
            'message': str(e)
        }, status=400)