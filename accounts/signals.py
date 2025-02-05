from django.db.models.signals import post_save
from django.dispatch import receiver
from django.db import transaction

@receiver(post_save, sender='accounts.Customer')
def handle_customer_post_save(sender, instance, created, **kwargs):
    if created:
        transaction.on_commit(lambda: instance.create_service_requests_from_records())