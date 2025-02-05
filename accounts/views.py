from django.shortcuts import render, redirect
from django.contrib.auth import login, logout, authenticate
from django.contrib.auth.decorators import login_required
from .forms import CustomerRegistrationForm
from service.models import ServiceRequest
from .models import Customer
from .forms import CustomerForm
from django.views.generic import ListView, CreateView, UpdateView, DeleteView
from django.contrib.auth.mixins import UserPassesTestMixin, LoginRequiredMixin
from django.urls import reverse_lazy
from .models import User
from django.contrib import messages
from django.http import JsonResponse, HttpResponse
from django.views.generic import TemplateView
from decimal import Decimal, InvalidOperation
from django.core.mail import send_mail, BadHeaderError
from django.contrib.auth.forms import PasswordResetForm
from django.template.loader import render_to_string
from django.db.models.query_utils import Q
from django.utils.http import urlsafe_base64_encode
from django.contrib.auth.tokens import default_token_generator
from django.utils.encoding import force_bytes

def register(request):
    if request.method == 'POST':
        form = CustomerRegistrationForm(request.POST)
        if form.is_valid():
            user = form.save()
            login(request, user)
            messages.success(request, 'ลงทะเบียนเรียบร้อยแล้ว')
            return redirect('home')
    else:
        form = CustomerRegistrationForm()
    return render(request, 'accounts/register.html', {'form': form})

@login_required
def profile(request):
    context = {
        'user': request.user
    }
    
    if request.user.user_type == 'service':
        context['service_requests'] = ServiceRequest.objects.all().order_by('-created_at')
    
    return render(request, 'accounts/profile.html', context)

@login_required
def edit_profile(request):
  if request.method == 'POST':
      # อัพเดทข้อมูลพื้นฐาน
      user = request.user
      user.phone = request.POST.get('phone')
      
      # จัดการรูปโปรไฟล์
      if 'profile_image' in request.FILES:
          print("Found profile image in request")  # เพิ่ม debug log
          if user.profile_image:
              # ลบรูปเก่าถ้ามี
              user.profile_image.delete()
          user.profile_image = request.FILES['profile_image']
          print(f"Profile image saved: {user.profile_image.name}")  # เพิ่ม debug log
      
      if user.user_type == 'technician':
          technician = user.customer
          technician.customer_name = request.POST.get('customer_name')
          technician.address = request.POST.get('address','')
          technician.save()
      
      # บันทึกข้อมูลผู้ใช้
      try:
          user.save()
          print("User saved successfully")  # เพิ่ม debug log
          messages.success(request, 'อัพเดทข้อมูลเรียบร้อยแล้ว')
      except Exception as e:
          print(f"Error saving user: {str(e)}")  # เพิ่ม debug log
          messages.error(request, f'เกิดข้อผิดพลาด: {str(e)}')
      
      # อัพเดทข้อมูลลูกค้า
      if user.user_type == 'customer':
          customer = user.customer
          customer.customer_name = request.POST.get('customer_name')
          customer.project_name = request.POST.get('project_name')
          customer.house_number = request.POST.get('house_number')
          customer.phone = request.POST.get('phone')
          customer.location = request.POST.get('location')
          customer.save()
      
      return redirect('accounts:profile')
  
  return render(request, 'accounts/edit_profile.html')

def login_view(request):
    if request.method == 'POST':
        username = request.POST['username']
        password = request.POST['password']
        user = authenticate(request, username=username, password=password)
        if user is not None:
            login(request, user)
            return redirect('home')
    return render(request, 'accounts/login.html')

@login_required
def logout_view(request):
    if request.method == 'POST':
        logout(request)
        return redirect('login')
    return redirect('home')

class ServiceStaffRequired(UserPassesTestMixin):
    def test_func(self):
        return self.request.user.user_type == 'service'

class CustomerListView(LoginRequiredMixin, ServiceStaffRequired, ListView):
    model = Customer
    template_name = 'accounts/customer_list.html'
    context_object_name = 'customers'

class CustomerCreateView(LoginRequiredMixin, ServiceStaffRequired, CreateView):
    model = Customer
    form_class = CustomerForm
    template_name = 'accounts/customer_form.html'
    success_url = reverse_lazy('accounts:customer_list')

    def form_valid(self, form):
        # สร้าง User account สำหรับลูกค้า
        user = User.objects.create_user(
            username=form.cleaned_data['phone'],  # ใช้เบอร์โทรเป็น username
            password=form.cleaned_data['phone'],  # ใช้เบอร์โทรเป็นรหัสผ่านเริ่มต้น
            user_type='customer'
        )
        form.instance.user = user
        return super().form_valid(form)

class CustomerUpdateView(LoginRequiredMixin, ServiceStaffRequired, UpdateView):
    model = Customer
    form_class = CustomerForm
    template_name = 'accounts/customer_form.html'
    success_url = reverse_lazy('accounts:customer_list')

class CustomerDeleteView(LoginRequiredMixin, ServiceStaffRequired, DeleteView):
    model = Customer
    template_name = 'accounts/customer_confirm_delete.html'
    success_url = reverse_lazy('accounts:customer_list')

class CustomerMapView(LoginRequiredMixin, TemplateView):
    template_name = 'accounts/customer_map_form.html'
    
    def post(self, request, *args, **kwargs):
        if request.user.user_type == 'customer':
            try:
                # รับค่าและตรวจสอบความถูกต้อง
                latitude = request.POST.get('latitude')
                longitude = request.POST.get('longitude')
                location = request.POST.get('location')

                if not latitude or not longitude:
                    return JsonResponse({
                        'status': 'error',
                        'message': 'กรุณาเลือกตำแหน่งบนแผนที่'
                    }, status=400)

                try:
                    # แปลงค่าเป็น Decimal
                    customer = request.user.customer
                    customer.latitude = Decimal(str(latitude))
                    customer.longitude = Decimal(str(longitude))
                    customer.location = location
                    customer.save()

                    return JsonResponse({
                        'status': 'success',
                        'message': 'บันทึกตำแหน่งเรียบร้อยแล้ว'
                    })

                except (ValueError, TypeError) as e:
                    return JsonResponse({
                        'status': 'error',
                        'message': f'รูปแบบพิกัดไม่ถูกต้อง: {str(e)}'
                    }, status=400)
                    
            except Exception as e:
                return JsonResponse({
                    'status': 'error',
                    'message': f'เกิดข้อผิดพลาด: {str(e)}'
                }, status=500)
                
        return JsonResponse({
            'status': 'error',
            'message': 'ไม่มีสิทธิ์ในการบันทึกข้อมูล'
        }, status=403)
    

def password_reset_request(request):
    if request.method == "POST":
        password_reset_form = PasswordResetForm(request.POST)
        if password_reset_form.is_valid():
            data = password_reset_form.cleaned_data['email']
            associated_users = User.objects.filter(Q(email=data))
            if associated_users.exists():
                for user in associated_users:
                    subject = "การรีเซ็ตรหัสผ่าน"
                    email_template_name = "accounts/password_reset_email.txt"
                    c = {
                        "email": user.email,
                        'domain': request.META['HTTP_HOST'],
                        'site_name': 'Your Site',
                        "uid": urlsafe_base64_encode(force_bytes(user.pk)),
                        "user": user,
                        'token': default_token_generator.make_token(user),
                        'protocol': 'https' if request.is_secure() else 'http',
                    }
                    email = render_to_string(email_template_name, c)
                    try:
                        send_mail(subject, email, 'admin@example.com', [user.email], fail_silently=False)
                    except BadHeaderError:
                        return HttpResponse('Invalid header found.')
                    return redirect("accounts:password_reset_done")
    password_reset_form = PasswordResetForm()
    return render(request=request, 
                  template_name="accounts/password_reset.html", 
                  context={"form":password_reset_form})