from django.contrib.auth.models import AbstractUser
from django.db import models
from django.utils import timezone
from django.db.models.signals import post_save
from django.dispatch import receiver


class User(AbstractUser):
    # เพิ่ม validator สำหรับ username
    username = models.CharField(
        max_length=150,
        unique=True,
        error_messages={
            'unique': 'ชื่อผู้ใช้นี้ถูกใช้งานแล้ว',
        },
        help_text='ใช้ชื่อจริงของท่านในการลงทะเบียน',
        verbose_name='ชื่อผู้ใช้'
    )
    USER_TYPE_CHOICES = (
        ('customer', 'ลูกค้า'),
        ('service', 'ฝ่ายบริการ'),
        ('technician', 'ช่าง'),
    )
    
    user_type = models.CharField(max_length=20, choices=USER_TYPE_CHOICES)
    phone = models.CharField(max_length=50, null=True, blank=True)
    address = models.TextField(blank=True)
    profile_image = models.ImageField(upload_to='profile_images/', null=True, blank=True)

class Customer(models.Model):
    PROBLEM_TYPES = [
        ('ELECTRIC', 'ไฟฟ้า'),
        ('AIRPLUS', 'แอร์พลัส'),
        ('EVCHARGER', 'EV ชาร์จเจอร์'),
    ]
    WARRANTY_STATUS = [
        ('ACTIVE', 'อยู่ในประกัน'),
        ('EXPIRED', 'หมดประกัน'),
        ('NONE', 'ไม่มีประกัน')
    ]
    user = models.OneToOneField(User, on_delete=models.CASCADE)
    project_name = models.CharField(max_length=100, verbose_name="ชื่อโครงการ")
    house_number = models.CharField(max_length=50, verbose_name="บ้านเลขที่")
    problem_type = models.CharField(max_length=20, choices=PROBLEM_TYPES, default='OTHER', verbose_name="ประเภทปัญหา")
    problem_description = models.TextField(
        verbose_name="รายละเอียดปัญหา",
        blank=True,
        null=True,
        help_text="กรุณาระบุรายละเอียดของปัญหาที่พบ"
    )
    warranty_status = models.CharField(
        max_length=10,
        choices=WARRANTY_STATUS,
        default='NONE',
        verbose_name="สถานะประกัน"
    )
    warranty_expiry_date = models.DateField(
        null=True,
        blank=True,
        verbose_name="วันหมดประกัน"
    )
    phone = models.CharField(max_length=50, null=True, blank=True, verbose_name="เบอร์โทร")
    # ลบ location ที่เป็น TextField ออก เพราะซ้ำซ้อนกับ CharField
    latitude = models.DecimalField(
        max_digits=9,
        decimal_places=6,
        null=True,
        blank=True,
        verbose_name="ละติจูด"
    )
    longitude = models.DecimalField(
        max_digits=9,
        decimal_places=6,
        null=True,
        blank=True,
        verbose_name="ลองจิจูด"
    )
    location = models.CharField(
        max_length=255,
        blank=True,
        null=True,
        verbose_name="ที่อยู่"
    )
    location_updates_count = models.PositiveIntegerField(
        default=0,
        verbose_name="จำนวนครั้งที่อัพเดทที่อยู่"
    )
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"{self.user.username}: {self.project_name} {self.house_number}"
    
    def save(self, *args, **kwargs):
        # ตรวจสอบและกำหนดสถานะประกันตาม project_type
        if self.problem_type in ['ELECTRIC', 'AIRPLUS', 'EVCHARGER']:
            # ตรวจสอบวันหมดประกัน
            if self.warranty_expiry_date:
                if timezone.now().date() <= self.warranty_expiry_date:
                    self.warranty_status = 'ACTIVE'
                else:
                    self.warranty_status = 'EXPIRED'
            else:
                # ถ้าไม่มีวันหมดประกัน ให้กำหนดเป็น 1 ปีนับจากวันที่บันทึก
                self.warranty_status = 'ACTIVE'
                self.warranty_expiry_date = timezone.now().date() + timezone.timedelta(days=365)
        else:
            self.warranty_status = 'NONE'
            self.warranty_expiry_date = None

        # บันทึกข้อมูลปกติ
        super().save(*args, **kwargs)
        
        # ย้าย import มาไว้ในเมธอด
        if self.problem_description and not kwargs.get('update_fields'):
            from service.models import ServiceRequest
            existing_request = ServiceRequest.objects.filter(
                customer=self,
                description=self.problem_description
            ).exists()
            
            if not existing_request:
                ServiceRequest.objects.create(
                    customer=self,
                    description=self.problem_description,
                    request_type='repair',
                    status='pending',
                    service_category=self.problem_type if self.problem_type in ['ELECTRIC', 'AIRPLUS'] else 'OTHER',
                    need_advice=True
                )

    def create_service_requests_from_records(self):
        """Method to create service requests from matching records"""
        from service.models import ServiceRecord, ServiceRequest

        matching_records = ServiceRecord.objects.filter(
            project_name=self.project_name,
            house_number=self.house_number
        ).order_by('-date')

        for record in matching_records:
            existing_request = ServiceRequest.objects.filter(
                customer=self,
                description=record.description,
                created_at__date=record.date
            ).exists()

            if not existing_request and record.description:
                ServiceRequest.objects.create(
                    customer=self,
                    request_type='repair',
                    description=record.description,
                    status='pending',
                    appointment_date=record.date,
                    appointment_time=record.time,
                    need_advice=True,
                    warranty_status=self.warranty_status,
                    created_at=timezone.now()
                )

        latest_record = matching_records.first()
        if latest_record:
            updated = False
            if latest_record.warranty_expiry:
                self.warranty_expiry_date = latest_record.warranty_expiry
                self.warranty_status = 'ACTIVE' if latest_record.warranty_expiry > timezone.now().date() else 'EXPIRED'
                updated = True
            if latest_record.customer_phone:
                self.phone = latest_record.customer_phone
                updated = True
            if updated:
                self.save(update_fields=['warranty_expiry_date', 'warranty_status', 'phone'])

@receiver(post_save, sender=Customer)
def handle_customer_post_save(sender, instance, created, **kwargs):
    """Signal handler for Customer post_save"""
    if created:
        from django.db import transaction
        transaction.on_commit(lambda: instance.create_service_requests_from_records())