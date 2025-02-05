from django import forms
from django.contrib.auth.forms import UserCreationForm
from .models import User, Customer
from service.models import ServiceRecord
from django.core.exceptions import ValidationError

'''
class CustomerRegistrationForm(UserCreationForm):
    project_name = forms.CharField(max_length=100, label="ชื่อโครงการ")
    house_number = forms.CharField(max_length=50, label="บ้านเลขที่") 
    phone = forms.CharField(max_length=50, required=False, label="เบอร์โทร", empty_value=None)
    location = forms.CharField(widget=forms.Textarea, label="ที่อยู่")
    problem_type = forms.ChoiceField(
        choices=Customer.PROBLEM_TYPES,
        label="ประเภทปัญหา"
    )
    problem_description = forms.CharField(
        widget=forms.Textarea(attrs={'rows': 3}),
        label="รายละเอียดปัญหา",
        required=False,
        help_text="กรุณาระบุรายละเอียดของปัญหาที่พบ"
    )
    
    class Meta:
        model = User
        fields = ('username', 'password1', 'password2')

    def save(self, commit=True):
        user = super().save(commit=False)
        user.user_type = 'customer'
        if commit:
            user.save()
            Customer.objects.create(
                user=user,
                project_name=self.cleaned_data['project_name'],
                house_number=self.cleaned_data['house_number'],
                phone=self.cleaned_data['phone'],
                location=self.cleaned_data['location'],
                problem_type=self.cleaned_data['problem_type'],
                problem_description=self.cleaned_data['problem_description']
            )
        return user
'''

class CustomerRegistrationForm(UserCreationForm):
    project_name = forms.CharField(max_length=100, label="ชื่อโครงการ")
    house_number = forms.CharField(max_length=50, label="บ้านเลขที่") 
    phone = forms.CharField(max_length=50, required=False, label="เบอร์โทร", empty_value=None)
    location = forms.CharField(widget=forms.Textarea, label="ที่อยู่")
    problem_type = forms.ChoiceField(
        choices=Customer.PROBLEM_TYPES,
        label="ประเภทปัญหา"
    )
    problem_description = forms.CharField(
        widget=forms.Textarea(attrs={'rows': 3}),
        label="รายละเอียดปัญหา",
        required=False,
        help_text="กรุณาระบุรายละเอียดของปัญหาที่พบ"
    )
    
    class Meta:
        model = User
        fields = ('username', 'password1', 'password2')

    def clean(self):
        cleaned_data = super().clean()
        project_name = cleaned_data.get('project_name')
        house_number = cleaned_data.get('house_number')

        # ตรวจสอบว่ามีข้อมูลบ้านนี้ในระบบแล้วหรือไม่
        existing_customer = Customer.objects.filter(
            project_name=project_name,
            house_number=house_number
        ).first()

        if existing_customer:
            raise ValidationError(
                'บ้านเลขที่นี้ในโครงการดังกล่าวมีการลงทะเบียนแล้ว กรุณาติดต่อเจ้าหน้าที่'
            )

        return cleaned_data

    def save(self, commit=True):
        user = super().save(commit=False)
        user.user_type = 'customer'
        
        if commit:
            user.save()
            
            # สร้าง Customer
            customer = Customer.objects.create(
                user=user,
                project_name=self.cleaned_data['project_name'],
                house_number=self.cleaned_data['house_number'],
                phone=self.cleaned_data['phone'],
                location=self.cleaned_data['location'],
                problem_type=self.cleaned_data['problem_type'],
                problem_description=self.cleaned_data['problem_description']
            )

            # ค้นหาข้อมูลที่ตรงกันใน ServiceRecord
            matching_record = ServiceRecord.objects.filter(
                project_name=customer.project_name,
                house_number=customer.house_number
            ).first()

            if matching_record:
                # อัพเดทข้อมูลใน matching record
                matching_record.customer = customer
                matching_record.customer_name = user.get_full_name() or user.username
                matching_record.customer_phone = customer.phone
                matching_record.description = customer.problem_description
                matching_record.save()
            else:
                # สร้าง ServiceRecord ใหม่
                ServiceRecord.objects.create(
                    customer=customer,
                    project_name=customer.project_name,
                    house_number=customer.house_number,
                    customer_name=user.get_full_name() or user.username,
                    customer_phone=customer.phone,
                    description=customer.problem_description,
                    status='pending'
                )

        return user

class CustomerForm(forms.ModelForm):
    username = forms.CharField(
        max_length=150,
        label="ชื่อผู้ใช้",
        disabled=True
    )

    class Meta:
        model = Customer
        fields = [
            'project_name', 
            'house_number', 
            'phone', 
            'location',
            'problem_type',
            'problem_description',
            'warranty_status',
            'warranty_expiry_date'
        ]
        widgets = {
            'location': forms.Textarea(attrs={'rows': 3}),
            'problem_type': forms.Select(attrs={'class': 'form-control'}),
            'problem_description': forms.Textarea(attrs={'rows': 3}),
            'warranty_status': forms.Select(attrs={'class': 'form-control', 'disabled': 'disabled'}),
            'warranty_expiry_date': forms.DateInput(attrs={'class': 'form-control', 'type': 'date', 'disabled': 'disabled'})
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if self.instance and self.instance.user:
            self.fields['username'].initial = self.instance.user.username