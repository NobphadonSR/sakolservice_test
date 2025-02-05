from django.db import models
from django.utils import timezone
from django.core.validators import MinValueValidator
from django.core.exceptions import ValidationError
from datetime import timedelta
from accounts.models import Customer
from django.db.models.signals import post_save
from django.dispatch import receiver

class ServiceRequest(models.Model):
    REQUEST_TYPES = [
        ('repair', 'แจ้งซ่อม'),
        ('install', 'ซื้ออะไหล่'),
        ('all_in', 'ต้องการแจ้งซ่อมและซื้ออะไหล่'),
    ]
    
    STATUS_CHOICES = [
        ('pending', 'รอดำเนินการ'),
        ('assigned', 'มอบหมายงานแล้ว'),
        ('pending_advice', 'รอคำปรึกษาจากช่าง'),
        ('advice_given', 'ให้คำปรึกษาแล้ว'),
        ('confirmed', 'ยืนยันการแจ้งซ่อม'),
        ('accepted', 'รับงาน'),
        ('traveling', 'กำลังเดินทาง'),
        ('arrived', 'ถึงจุดหมาย'),
        ('fixing', 'กำลังแก้ไข'),
        ('completed', 'จบงาน'),
        ('cancelled', 'ยกเลิก'),
        ('rescheduled', 'เลื่อนนัด'),
    ]

    WARRANTY_STATUS = [
        ('in_warranty', 'อยู่ในประกัน'),
        ('out_of_warranty', 'ไม่อยู่ในประกัน'),
        ('pending_warranty', 'รอการตัดสินใจ'),
    ]

    SERVICE_TYPES = [
        ('normal', 'ระบบไฟปกติ'),
        ('full_checkup', 'ระบบ Full Check Up'),
        ('air_flow', 'ระบบ Air flow/Air Plus'),
        ('checkup_air_plus', 'ระบบ Check up Program Air plus'),
    ]


    # เพิ่ม choices ใหม่ต่อจาก SERVICE_TYPES
    SERVICE_CATEGORIES = [
        ('ELECTRICAL', 'ตู้ไฟ'),
        ('AIRPLUS', 'Air Plus'),
        ('OTHER', 'บริการอื่นๆ')
    ]
    
    SERVICE_LEVELS = [
        ('NORMAL', 'บริการแบบปกติ'),
        ('FULL', 'บริการแบบ Full Check up')
    ]

    customer = models.ForeignKey('accounts.Customer', on_delete=models.CASCADE, related_name='service_requests')
    request_type = models.CharField(max_length=20, choices=REQUEST_TYPES)
    technician = models.ForeignKey('accounts.User', on_delete=models.SET_NULL, null=True, blank=True, related_name='assigned_requests')
    appointment_date = models.DateField(null=True, blank=True)
    appointment_time = models.TimeField(null=True, blank=True)  # เพิ่มฟิลด์นี้
    description = models.TextField(
        verbose_name='รายละเอียดปัญหา',
        help_text='อ้างอิงจากรายละเอียดปัญหาที่ลูกค้าแจ้งตอนลงทะเบียน'
    )
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='pending')
    created_at = models.DateTimeField(auto_now_add=True, verbose_name='วันที่สร้าง')
    is_confirmed = models.BooleanField(default=False, verbose_name='ยืนยันโดยฝ่ายบริการ')
    warranty_status = models.CharField(max_length=20, choices=WARRANTY_STATUS, default='pending_warranty', verbose_name='สถานะประกัน')
    
    # เพิ่มฟิลด์ใหม่
    need_advice = models.BooleanField(default=False, verbose_name='ต้องการคำแนะนำจากช่าง',help_text='เลือกตัวเลือกนี้หากต้องการให้ช่างแนะนำก่อนดำเนินการ')
    customer_confirmed = models.BooleanField(default=False,verbose_name='ลูกค้ายืนยันการดำเนินการ')
    technician_advice = models.TextField(blank=True,null=True,verbose_name='คำแนะนำจากช่าง')
    estimated_cost = models.DecimalField(max_digits=10,decimal_places=2,null=True,blank=True,verbose_name='ประมาณการค่าใช้จ่าย')
    # เพิ่มฟิลด์ใหม่สำหรับการจัดการค่าใช้จ่าย
    cost_note = models.TextField(
        blank=True, 
        verbose_name="หมายเหตุค่าใช้จ่าย"
    )
    cost_updated_by = models.ForeignKey(
        'accounts.User',
        on_delete=models.SET_NULL,
        null=True,
        related_name='cost_updates',
        verbose_name="ผู้กำหนดค่าใช้จ่าย"
    )
    cost_updated_at = models.DateTimeField(
        null=True, 
        blank=True,
        verbose_name="วันที่กำหนดค่าใช้จ่าย"
    )
    service_type = models.CharField(max_length=50, choices=SERVICE_TYPES, null=True, blank=True, verbose_name='ประเภทการซ่อม')

    # เพิ่มฟิลด์ใหม่
    warranty_start_date = models.DateField(null=True, blank=True, verbose_name='วันที่เริ่มประกัน')
    warranty_end_date = models.DateField(null=True, blank=True, verbose_name='วันที่สิ้นสุดประกัน')

    # เพิ่มฟิลด์ใหม่ต่อจากฟิลด์เดิม
    service_category = models.CharField(
        max_length=20, 
        choices=SERVICE_CATEGORIES,
        null=True,
        blank=True,
        verbose_name="ประเภทบริการ"
    )
    service_level = models.CharField(
        max_length=10, 
        choices=SERVICE_LEVELS,
        null=True,
        blank=True,
        verbose_name="ระดับบริการ"
    )
    calculated_price = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        null=True,
        blank=True,
        verbose_name="ราคาประเมิน"
    )
    service_record = models.ForeignKey(
        'ServiceRecord',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='service_requests',
        verbose_name='บันทึกการบริการ'
    )
    project_code = models.CharField(
            max_length=50,
            blank=True,
            null=True,
            verbose_name='รหัสโครงการ'
    )

    def check_warranty_status(self):
        """ตรวจสอบสถานะประกันอัตโนมัติ"""
        today = timezone.now().date()
        
        # แปลงค่าสถานะประกันระหว่าง Customer และ ServiceRequest
        warranty_status_mapping = {
            'ACTIVE': 'in_warranty',
            'EXPIRED': 'out_of_warranty',
            'NONE': 'pending_warranty'
        }
        
        # ตรวจสอบสถานะประกันจาก Customer
        customer = self.customer
        self.warranty_status = warranty_status_mapping.get(
            customer.warranty_status, 
            'pending_warranty'
        )
        
        # อัพเดทวันที่ประกัน
        if customer.warranty_status == 'ACTIVE':
            self.warranty_start_date = today
            self.warranty_end_date = customer.warranty_expiry_date

    def save(self, *args, **kwargs):
        is_new = self._state.adding
        
        # คำนวณราคาอัตโนมัติ
        if self.service_category:
            self.calculated_price = self.calculate_service_fee()
        
        # ตรวจสอบการซื้ออะไหล่ใหม่
        if self.request_type in ['install', 'all_in'] and (is_new or not self.warranty_start_date):
            today = timezone.now().date()
            self.warranty_start_date = today
            self.warranty_end_date = today + timedelta(days=365)
            self.warranty_status = 'in_warranty'
            
            # อัพเดทข้อมูลลูกค้า
            if self.customer:
                self.customer.warranty_status = 'ACTIVE'
                self.customer.warranty_expiry_date = self.warranty_end_date
                self.customer.save(update_fields=['warranty_status', 'warranty_expiry_date'])
        
        # ตรวจสอบสถานะประกัน
        self.check_warranty_status()
        
        # ตรวจสอบการนัดหมาย
        if self.appointment_date and self.appointment_time:
            if self.check_appointment_conflict(self.appointment_date, self.appointment_time):
                raise ValidationError('มีการนัดหมายซ้ำซ้อนกับช่างท่านนี้')
            
            if not self.is_within_service_hours(self.appointment_time):
                raise ValidationError('เวลานัดหมายต้องอยู่ในช่วง 10:00 น., 10:30 น., 14:00 น., 14:30 น.')

        # เพิ่มการอัพเดทข้อมูลประกันของลูกค้า
        if self.warranty_status == 'in_warranty':
            self.update_customer_warranty()
        
        # ถ้าเป็นการสร้างใหม่และไม่มี description
        if not self.pk and not self.description:
            # ใช้ problem_description จาก Customer
            self.description = self.customer.problem_description or ''
        
        super().save(*args, **kwargs)
        # อัพเดทสถานะใน ServiceRecord หลังจากบันทึก ServiceRequest
        if self.service_record:
            self.service_record.update_status_from_request()
    
    def set_warranty(self, start_date=None):
        """ตั้งค่าประกัน 1 ปี"""
        if start_date is None:
            start_date = timezone.now().date()
        
        # อัพเดทข้อมูลการรับประกัน
        self.warranty_start_date = start_date
        self.warranty_end_date = start_date + timedelta(days=365)
        self.warranty_status = 'in_warranty'
        
        # อัพเดทข้อมูลลูกค้าด้วย
        if self.customer:
            self.customer.warranty_status = 'ACTIVE'
            self.customer.warranty_expiry_date = self.warranty_end_date
            self.customer.save(update_fields=['warranty_status', 'warranty_expiry_date'])
        
        self.save(update_fields=['warranty_start_date', 'warranty_end_date', 'warranty_status'])

    @property
    def remaining_warranty_days(self):
        """คำนวณจำนวนวันประกันที่เหลือ"""
        if not self.warranty_end_date:
            return 0
            
        today = timezone.now().date()
        if today > self.warranty_end_date:
            return 0
            
        return (self.warranty_end_date - today).days

    def check_appointment_conflict(self, date, time):
        """ตรวจสอบการซ้ำซ้อนของการนัดหมาย"""
        if not self.technician:
            return False
            
        conflicts = ServiceRequest.objects.filter(
            technician=self.technician,
            appointment_date=date,
            appointment_time=time
        ).exclude(id=self.id)
        
        return conflicts.exists()

    def calculate_service_fee(self):
        """คำนวณค่าบริการตามประเภทงาน"""
        if not self.service_type:
            return 0
            
        base_fee = {
            'normal': 500,
            'full_checkup': 1500,
            'air_flow': 2000,
            'checkup_air_plus': 2500
        }.get(self.service_type, 0)
        
        # เพิ่มค่าบริการตามจำนวนเครื่อง
        if self.ac_count:
            base_fee *= self.ac_count
            
        return base_fee

    def is_within_service_hours(self, time):
        """ตรวจสอบว่าอยู่ในเวลาทำการหรือไม่"""
        if not time:
            return True
            
        # กำหนดเวลาทำการ 8:00-17:00
        service_start = time.replace(hour=8, minute=0)
        service_end = time.replace(hour=17, minute=0)
        
        return service_start <= time <= service_end

    def get_customer_info(self):
        """ฟังก์ชันสำหรับดึงข้อมูลลูกค้า"""
        if self.customer:
            return {
                'customer_name': self.customer.user.username if self.customer.user else '',
                'phone': self.customer.phone or '',
                'address': self.customer.location or '',
                'project_name': self.customer.project_name,
                'house_number': self.customer.house_number,
                'warranty_status': self.customer.warranty_status
            }
        return {}

    def update_customer_warranty(self):
        """อัพเดทข้อมูลประกันของลูกค้า"""
        if self.customer and self.warranty_status == 'in_warranty':
            self.customer.warranty_status = 'ACTIVE'
            self.customer.warranty_expiry_date = self.warranty_end_date
            self.customer.save(update_fields=['warranty_status', 'warranty_expiry_date'])

    class Meta:
        ordering = ['-created_at']
        verbose_name = 'การแจ้งซ่อม'
        verbose_name_plural = 'การแจ้งซ่อม'

    def __str__(self):
        return f"{self.get_request_type_display()} - {self.customer}"

class ServiceProposal(models.Model):
    service_request = models.ForeignKey(
        ServiceRequest, 
        on_delete=models.CASCADE,
        related_name='service_proposals'  # เปลี่ยนจาก proposals เป็น service_proposals
    )
    technician = models.ForeignKey(
        'accounts.User',
        on_delete=models.CASCADE
    )
    description = models.TextField()
    estimated_cost = models.DecimalField(max_digits=10, decimal_places=2)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']

class ServiceImage(models.Model):
    service_request = models.ForeignKey(ServiceRequest, on_delete=models.CASCADE, related_name='service_images')
    image = models.ImageField(upload_to='service_images/')
    description = models.TextField(blank=True)
    uploaded_at = models.DateTimeField(auto_now_add=True)
    image_hash = models.CharField(max_length=64, blank=True)  # เพิ่มฟิลด์นี้

    class Meta:
        ordering = ['-uploaded_at']
        unique_together = ['service_request', 'image_hash']  # เปลี่ยนจาก image เป็น image_hash

    def generate_hash(self):
        import hashlib
        if self.image:
            # สร้าง hash จากเนื้อหาของไฟล์
            md5hash = hashlib.md5()
            for chunk in self.image.chunks():
                md5hash.update(chunk)
            return md5hash.hexdigest()
        return ''

    def save(self, *args, **kwargs):
        if not self.pk:  # ถ้าเป็นการสร้างใหม่
            # ตรวจสอบจำนวนรูปภาพ
            current_images = ServiceImage.objects.filter(
                service_request=self.service_request
            ).count()
            if current_images >= 6:
                raise ValidationError('ไม่สามารถอัพโหลดรูปภาพเกิน 6 รูปได้')
            
            # สร้าง hash และตรวจสอบรูปซ้ำ
            self.image_hash = self.generate_hash()
            if ServiceImage.objects.filter(
                service_request=self.service_request,
                image_hash=self.image_hash
            ).exists():
                raise ValidationError('รูปภาพนี้ถูกอัพโหลดไปแล้ว')

        super().save(*args, **kwargs)

class ServiceRecord(models.Model):
    sequence = models.IntegerField(verbose_name='ลำดับ', null=True)
    completion_status = models.BooleanField(default=False, verbose_name='สถานะจบงาน', null=True)
    year = models.CharField(max_length=4, verbose_name='ปี พ.ศ.', null=True)
    date = models.DateField(verbose_name='วันที่', null=True)
    month = models.IntegerField(verbose_name='เดือน', null=True, blank=True)
    time = models.TimeField(verbose_name='เวลา', null=True, blank=True)
    job_number = models.CharField(max_length=50, verbose_name='เลขงาน', null=True)
    bill_number = models.CharField(max_length=50, blank=True, null=True, verbose_name='เลขที่บิล')
    customer = models.ForeignKey(
        Customer, 
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='service_records'
    )
    technician_name = models.CharField(max_length=100, blank=True, verbose_name='ชื่อช่าง', null=True)
    technician_phone = models.CharField(max_length=20, blank=True, verbose_name='เบอร์ติดต่อช่าง', null=True)
    project_code = models.CharField(max_length=50, blank=True, verbose_name='รหัสโครงการ', null=True)
    project_name = models.CharField(max_length=100, verbose_name='โครงการ', null=True)
    house_number = models.CharField(max_length=50, null=True, verbose_name='บ้านเลขที่')
    plot_number = models.CharField(max_length=50, null=True, verbose_name='แปลง')
    house_type = models.CharField(max_length=50, null=True, verbose_name='แบบบ้าน')
    transfer_date = models.DateField(null=True, blank=True, verbose_name='วันที่โอน')
    warranty_expiry = models.DateField(null=True, blank=True, verbose_name='วันที่หมดประกัน')
    description = models.TextField(blank=True, default='', verbose_name='อาการที่แจ้ง', null=True)
    status = models.CharField(max_length=50, verbose_name='สถานะ', null=True)
    appointment_date = models.DateField(null=True, blank=True, verbose_name='วันนัด')
    appointment_time = models.TimeField(null=True, blank=True, verbose_name='เวลานัด')
    equipment_status = models.TextField(blank=True, default='', verbose_name='วัสดุ/อุปกรณ์ที่ผิดปกติ', null=True)
    cause_found = models.TextField(blank=True, default='', verbose_name='สาเหตุที่ตรวจพบ', null=True)
    solution = models.TextField(blank=True, default='', verbose_name='การแก้ไข', null=True)
    technician_names = models.CharField(max_length=200, blank=True, verbose_name='รายชื่อช่าง', null=True)
    notes = models.TextField(blank=True,default='', verbose_name='หมายเหตุ', null=True)
    amount = models.DecimalField(max_digits=10, decimal_places=2, default=0, verbose_name='จำนวนเงิน', null=True)
    service_images = models.TextField(blank=True, default='', verbose_name='ลิงก์รูปภาพ', null=True)
    additional_notes = models.TextField(blank=True, default='', verbose_name='หมายเหตุเพิ่มเติม', null=True)
    customer_name = models.CharField(max_length=100, blank=True, verbose_name='ชื่อลูกค้า', null=True)
    customer_phone = models.CharField(max_length=15, blank=True, verbose_name='เบอร์ติดต่อ', null=True)
    imported = models.BooleanField(default=False)

    class Meta:
        ordering = ['-date', '-time']
        verbose_name = 'บันทึกการบริการ'
        verbose_name_plural = 'บันทึกการบริการ'

    def update_status_from_request(self):
        """อัพเดทสถานะจาก ServiceRequest ล่าสุด"""
        latest_request = self.service_requests.last()
        if latest_request:
            if latest_request.status == 'completed':
                self.status = 'จบงาน'
                self.completion_status = True
            else:
                self.status = latest_request.get_status_display()
                self.completion_status = False
            self.save(update_fields=['status', 'completion_status'])

    def __str__(self):
        return f"{self.job_number} - {self.customer_name}"

class TechnicianProposal(models.Model):
    service_request = models.ForeignKey(
        ServiceRequest, 
        on_delete=models.CASCADE,
        related_name='technician_proposals'  # เปลี่ยนจาก proposals เป็น technician_proposals
    )
    technician = models.ForeignKey(
        'accounts.User',
        on_delete=models.CASCADE
    )
    description = models.TextField()
    estimated_cost = models.DecimalField(max_digits=10, decimal_places=2)
    is_approved = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']

class TechnicianJobStatus(models.Model):
    TECHNICIAN_STATUS_CHOICES = [
        ('assigned', 'ได้รับมอบหมายงาน'),
        ('confirmed', 'ยืนยันการแจ้งซ่อม'),
        ('accepted', 'รับงาน'),
        ('traveling', 'กำลังเดินทาง'),
        ('arrived', 'ถึงจุดหมาย'),
        ('fixing', 'กำลังแก้ไข'),
        ('completed', 'จบงาน'),
        ('cancelled', 'ยกเลิก'),
        ('rescheduled', 'เลื่อนนัด'),
    ]

    service_request = models.ForeignKey(ServiceRequest, on_delete=models.CASCADE, related_name='status_updates')
    technician = models.ForeignKey('accounts.User', on_delete=models.CASCADE, related_name='status_updates')
    status = models.CharField(max_length=20, choices=TECHNICIAN_STATUS_CHOICES, verbose_name='สถานะ')
    notes = models.TextField(blank=True, verbose_name='หมายเหตุ')
    created_at = models.DateTimeField(auto_now_add=True, verbose_name='เวลาอัพเดท')

    class Meta:
        ordering = ['-created_at']
        verbose_name = 'สถานะงานช่าง'
        verbose_name_plural = 'สถานะงานช่าง'

    def __str__(self):
        return f"อัพเดทสถานะสำหรับ {self.service_request}"
    
    def save(self, *args, **kwargs):
        # บันทึก TechnicianJobStatus
        super().save(*args, **kwargs)
        
        # อัพเดทสถานะใน ServiceRequest
        self.service_request.status = self.status
        self.service_request.save()

class TechnicianResponse(models.Model):
    service_request = models.ForeignKey(
        ServiceRequest,
        on_delete=models.CASCADE,
        related_name='technician_responses'
    )
    description = models.TextField(
        verbose_name='รายละเอียดการตอบกลับ',
        null=True,  # อนุญาตให้เป็น null ได้
        blank=True  # อนุญาตให้เว้นว่างได้ในฟอร์ม
    )
    service_type = models.CharField(
        max_length=50,
        choices=ServiceRequest.SERVICE_TYPES,
        null=True,
        blank=True,
        verbose_name='ประเภทการซ่อม'
    )
    estimated_cost = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        null=True,
        blank=True,
        verbose_name='ประมาณการค่าใช้จ่าย'
    )
    created_at = models.DateTimeField(
        default=timezone.now,
        verbose_name='วันที่ตอบกลับ'
    )

    class Meta:
        ordering = ['-created_at']
        verbose_name = 'การตอบกลับของช่าง'
        verbose_name_plural = 'การตอบกลับของช่าง'

    def __str__(self):
        return f"คำตอบจากช่างสำหรับ {self.service_request}"

class ServiceRecordHistory(models.Model):
    service_record = models.ForeignKey(
        ServiceRecord,
        on_delete=models.CASCADE,
        related_name='history'
    )
    modified_by = models.ForeignKey(
        'accounts.User',
        on_delete=models.SET_NULL,
        null=True
    )
    modified_fields = models.JSONField(
        help_text='บันทึกฟิลด์ที่มีการเปลี่ยนแปลง'
    )
    action = models.CharField(
        max_length=20,
        choices=[
            ('create', 'สร้าง'),
            ('update', 'แก้ไข'),
            ('delete', 'ลบ')
        ]
    )
    description = models.TextField(
        blank=True,
        help_text='รายละเอียดการเปลี่ยนแปลง'
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']
        verbose_name = 'ประวัติการแก้ไข'
        verbose_name_plural = 'ประวัติการแก้ไข'

    def __str__(self):
        return f'{self.service_record} - {self.action} by {self.modified_by} at {self.created_at}'