import os
from django.core.management.base import BaseCommand
from django.contrib.auth import get_user_model
from accounts.models import CustomUser

class Command(BaseCommand):
    help = "Creates a superuser from environment variables if one doesn't already exist"

    def handle(self, *args, **kwargs):
        User = get_user_model()
        
        # --- Get credentials from environment variables ---
        phone = os.environ.get('ADMIN_PHONE', '+256700000000')
        email = os.environ.get('ADMIN_EMAIL')
        password = os.environ.get('ADMIN_PASSWORD')

        # --- Validate that variables are set ---
        if not password:
            self.stdout.write(self.style.ERROR('ADMIN_PASSWORD must be set in your .env file.'))
            return

        user, created = CustomUser.objects.update_or_create(
            phone=phone,
            defaults={
                'email': email or 'admin@schoolrun.ng',
                'is_staff': True,
                'is_superuser': True,
                'role': CustomUser.Role.ADMIN,
                'full_name': "Super Admin User",
            }
        )
        if created:
            user.set_password(password)
            user.save()
            self.stdout.write(self.style.SUCCESS(f'Superuser created successfully with phone {phone}.'))
        else:
            self.stdout.write(self.style.SUCCESS(f'Superuser updated successfully.'))
