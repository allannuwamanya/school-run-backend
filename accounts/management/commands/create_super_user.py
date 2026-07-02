from django.core.management.base import BaseCommand
from django.contrib.auth import get_user_model
from accounts.models import CustomUser
import os # <-- Import the os module

class Command(BaseCommand):
    help = "Creates a superuser from environment variables if one doesn't already exist"

    def handle(self, *args, **kwargs):
        User = get_user_model()
        
        # --- Get credentials from environment variables ---
        email = os.environ.get('ADMIN_EMAIL')
        password = os.environ.get('ADMIN_PASSWORD')

        # --- Validate that the variables are set ---
        if not email or not password:
            self.stdout.write(self.style.ERROR('ADMIN_EMAIL and ADMIN_PASSWORD must be set in your .env file.'))
            return

        user, created = CustomUser.objects.update_or_create(
                    email=email,
                    defaults={
                        'email': email,
                        'is_staff': True,
                        'is_admin': True,
                        'is_superuser': True,
                        'full_name':"Super Admin User",

                    }
                )
        if created:
            user.set_password(password)
            user.save()
            self.stdout.write(self.style.SUCCESS(f'Superuser  created successfully.'))
        else:
            self.stdout.write(self.style.SUCCESS(f'Superuser  updated successfully.'))
