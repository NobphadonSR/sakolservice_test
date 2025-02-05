from django import forms
from .models import ServiceRequest, ServiceRecord
from django.utils import timezone

class ServiceRequestForm(forms.ModelForm):
    APPOINTMENT_TIMES = [
        ('10:00', '10:00'),
        ('10:30', '10:30'),
        ('14:00', '14:00'),
        ('14:30', '14:30'),
    ]

    appointment_time = forms.TimeField(
        widget=forms.Select(choices=APPOINTMENT_TIMES),
        help_text='เลือกเวลานัดหมายที่สะดวก'
    )

    warranty_check = forms.BooleanField(
        required=False,
        label='ตรวจสอบประกัน',
        widget=forms.CheckboxInput(attrs={'class': 'form-check-input'})
    )

    class Meta:
        model = ServiceRequest
        fields = [
            'request_type',
            'service_category',
            'description',
            'appointment_date',
            'appointment_time',
        ]
        help_texts = {
            'request_type': 'เลือกประเภทงานที่ต้องการ',
            'service_category': 'เลือกประเภทบริการที่เกี่ยวข้อง',
            'description': 'กรุณาระบุอาการหรือปัญหาที่พบให้ชัดเจน',
            'appointment_date': 'เลือกวันที่สะดวกให้ช่างเข้าตรวจสอบ',
            'appointment_time': 'เลือกช่วงเวลาที่สะดวก',
        }
        widgets = {
            'description': forms.Textarea(attrs={
                'rows': 4,
                'class': 'form-control',
                'required': True,
            }),
            'appointment_date': forms.DateInput(attrs={
                'type': 'date',
                'class': 'form-control',
                'required': True,
            }),
            'appointment_time': forms.TimeInput(attrs={
                'type': 'time',
                'class': 'form-control',
                'required': True,
            }),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['request_type'].required = True
        self.fields['service_category'].required = True

        for field in self.fields:
            if isinstance(self.fields[field].widget, forms.CheckboxInput):
                continue
            self.fields[field].widget.attrs.update({
                'class': 'form-control'
            })

    def clean(self):
        cleaned_data = super().clean()
        
        appointment_date = cleaned_data.get('appointment_date')
        appointment_time = cleaned_data.get('appointment_time')

        if appointment_date and appointment_time:
            if not (8 <= appointment_time.hour < 17):
                raise forms.ValidationError(
                    'กรุณาเลือกเวลานัดหมายระหว่าง ตอนเช้า 10:00-10:30 ตอนบ่าย 14:00-14:30'
                )
                
            if appointment_date < timezone.now().date():
                raise forms.ValidationError(
                    'ไม่สามารถเลือกวันที่ในอดีตได้'
                )

        return cleaned_data

    def save(self, commit=True):
        instance = super().save(commit=False)
        
        if instance.service_category:
            instance.calculated_price = instance.calculate_service_fee()
            
        if self.cleaned_data.get('warranty_check'):
            instance.check_warranty_status()
            
        if commit:
            instance.save()
        return instance

class ServiceRecordForm(forms.ModelForm):
    # เพิ่มฟิลด์ customer_phone แยก
    customer_phone = forms.CharField(
        max_length=20,
        required=False,
        label='เบอร์โทรลูกค้า',
        widget=forms.TextInput(attrs={'class': 'form-control'})
    )

    # เพิ่มฟิลด์ customer_name แบบ read-only เพื่อแสดงชื่อลูกค้า
    customer_name = forms.CharField(
        required=False,
        label='ชื่อลูกค้า',
        widget=forms.TextInput(attrs={
            'class': 'form-control',
            'readonly': 'readonly'
        })
    )

    class Meta:
        model = ServiceRecord
        fields = [
            # ข้อมูลพื้นฐาน
            'sequence',
            'completion_status',
            'year',
            'date',
            'month',
            'time',
            
            # ข้อมูลงานและบิล
            'job_number',
            'bill_number',
            
            # ข้อมูลลูกค้าและเจ้าหน้าที่
            'customer',
            'technician_name',
            'technician_phone',
            
            # ข้อมูลโครงการและบ้าน
            'project_code',
            'project_name',
            'house_number',
            'plot_number',
            'house_type',
            
            # วันที่สำคัญ
            'transfer_date',
            'warranty_expiry',
            
            # รายละเอียดการบริการ
            'description',
            'status',
            'appointment_date',
            'appointment_time',
            
            # รายละเอียดการตรวจสอบและซ่อม
            'equipment_status',
            'cause_found',
            'solution',
            'technician_names',
            
            # ข้อมูลเพิ่มเติม
            'notes',
            'amount',
            'service_images',
            'additional_notes',
        ]
        widgets = {
            # ปรับปรุง widgets เพื่อเพิ่ม class และ attributes ที่จำเป็น
            'description': forms.Textarea(attrs={
                'rows': 3,
                'class': 'form-control',
                'placeholder': 'กรอกอาการที่ลูกค้าแจ้ง'
            }),
            'cause_found': forms.Textarea(attrs={
                'rows': 3,
                'class': 'form-control',
                'placeholder': 'ระบุสาเหตุที่ตรวจพบ'
            }),
            'solution': forms.Textarea(attrs={
                'rows': 3,
                'class': 'form-control',
                'placeholder': 'อธิบายวิธีการแก้ไข'
            }),
            'notes': forms.Textarea(attrs={
                'rows': 3,
                'class': 'form-control'
            }),
            'additional_notes': forms.Textarea(attrs={
                'rows': 3,
                'class': 'form-control'
            }),
            'service_images': forms.Textarea(attrs={
                'rows': 2,
                'class': 'form-control',
                'placeholder': 'วางลิงก์รูปภาพ แต่ละลิงก์ขึ้นบรรทัดใหม่'
            }),
            
            # เพิ่ม class และ attributes สำหรับ date inputs
            'date': forms.DateInput(attrs={
                'type': 'date',
                'class': 'form-control'
            }),
            'transfer_date': forms.DateInput(attrs={
                'type': 'date',
                'class': 'form-control'
            }),
            'warranty_expiry': forms.DateInput(attrs={
                'type': 'date',
                'class': 'form-control'
            }),
            'appointment_date': forms.DateInput(attrs={
                'type': 'date',
                'class': 'form-control'
            }),
            
            # เพิ่ม class สำหรับ time inputs
            'time': forms.TimeInput(attrs={
                'type': 'time',
                'class': 'form-control'
            }),
            'appointment_time': forms.TimeInput(attrs={
                'type': 'time',
                'class': 'form-control'
            }),
            
            # ปรับปรุง status เป็น Select
            'status': forms.Select(attrs={
                'class': 'form-control'
            }, choices=[
                ('pending', 'รอดำเนินการ'),
                ('in_progress', 'กำลังดำเนินการ'),
                ('completed', 'เสร็จสิ้น'),
                ('cancelled', 'ยกเลิก')
            ]),
            
            # คงไว้เหมือนเดิมสำหรับ fields อื่นๆ
            'completion_status': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
            'sequence': forms.NumberInput(attrs={'min': 0, 'class': 'form-control'}),
            'month': forms.NumberInput(attrs={'min': 1, 'max': 12, 'class': 'form-control'}),
            'amount': forms.NumberInput(attrs={'step': '0.01', 'class': 'form-control'}),
            'year': forms.TextInput(attrs={
                'maxlength': 4,
                'pattern': '[0-9]{4}',
                'class': 'form-control'
            }),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        
        # อัพเดทข้อมูลลูกค้า
        if self.instance and self.instance.customer:
            self.fields['customer_phone'].initial = self.instance.customer.phone
            self.fields['customer_name'].initial = (
                self.instance.customer.user.get_full_name() or 
                self.instance.customer.user.username
            )

        # ทำให้ทุก field เป็น optional
        for field in self.fields:
            self.fields[field].required = False
            
            # เพิ่ม class Bootstrap ยกเว้น checkbox
            if not isinstance(self.fields[field].widget, forms.CheckboxInput):
                self.fields[field].widget.attrs.update({'class': 'form-control'})

    def clean(self):
        cleaned_data = super().clean()
        # เพิ่มการ validate ข้อมูล
        if cleaned_data.get('date'):
            # อัพเดท month และ year อัตโนมัติ
            cleaned_data['month'] = cleaned_data['date'].month
            cleaned_data['year'] = str(cleaned_data['date'].year)
        return cleaned_data

    def save(self, commit=True):
        instance = super().save(commit=False)
        
        # อัพเดทข้อมูลลูกค้า
        if instance.customer and self.cleaned_data.get('customer_phone'):
            instance.customer.phone = self.cleaned_data['customer_phone']
            instance.customer.save()
            
        if commit:
            instance.save()
        return instance