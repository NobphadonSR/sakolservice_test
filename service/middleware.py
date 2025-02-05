# สร้างไฟล์ใหม่ middleware.py
from django.core.cache import cache
from django.http import HttpResponseForbidden

class SimpleRateLimitMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        if request.path.startswith('/service/records/'):
            client_ip = request.META.get('REMOTE_ADDR')
            cache_key = f'request_count_{client_ip}'
            request_count = cache.get(cache_key, 0)
            
            # จำกัด 100 ครั้งต่อชั่วโมง
            if request_count > 100:
                return HttpResponseForbidden('ขออภัย คุณเข้าชมข้อมูลเกินกำหนด กรุณารอสักครู่')
            
            cache.set(cache_key, request_count + 1, 3600)  # หมดอายุใน 1 ชั่วโมง
        
        return self.get_response(request)