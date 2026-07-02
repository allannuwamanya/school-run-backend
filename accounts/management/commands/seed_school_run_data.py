from django.core.management.base import BaseCommand
from django.utils.text import slugify
from zones.models import Zone
from payments.models import SubscriptionPlan, ScheduledReport
from django.utils import timezone


class Command(BaseCommand):
    help = "Seeds initial database data for zones, subscription plans, and scheduled reports"

    def handle(self, *args, **kwargs):
        # 1. Seed Zones
        zones_data = [
            {"name": "Lekki", "description": "Lekki Phase 1, Phase 2, and environs"},
            {"name": "Ajah", "description": "Ajah, Badore, Sangotedo, and environs"},
            {"name": "Ikeja", "description": "Ikeja, Allen Avenue, GRA, and environs"},
            {"name": "Victoria Island", "description": "Victoria Island, Oniru, and environs"},
            {"name": "Surulere", "description": "Surulere, Adeniran Ogunsanya, and environs"},
            {"name": "Yaba", "description": "Yaba, Ebute Metta, Sabo, and environs"},
            {"name": "Gbagada", "description": "Gbagada Phase 1, Phase 2, and environs"},
        ]

        self.stdout.write("Seeding Zones...")
        for zone_info in zones_data:
            zone, created = Zone.objects.get_or_create(
                slug=slugify(zone_info["name"]),
                defaults={
                    "name": zone_info["name"],
                    "description": zone_info["description"],
                    "is_active": True
                }
            )
            if created:
                self.stdout.write(self.style.SUCCESS(f"Created zone: {zone.name}"))
            else:
                self.stdout.write(self.style.WARNING(f"Zone {zone.name} already exists"))

        # 2. Seed Subscription Plans
        plans_data = [
            {
                "name": "Standard Plan",
                "monthly_cost": 15000.00,
                "max_children": 1,
                "priority_matching": False,
                "features": ["1 Child covered", "Standard driver matching", "Email trip summaries"],
            },
            {
                "name": "Premium Plan",
                "monthly_cost": 25000.00,
                "max_children": 2,
                "priority_matching": True,
                "features": ["Up to 2 Children covered", "Priority driver matching", "SMS alerts", "Real-time map tracking"],
            },
            {
                "name": "Family+ Plan",
                "monthly_cost": 40000.00,
                "max_children": 4,
                "priority_matching": True,
                "features": ["Up to 4 Children covered", "Priority driver matching", "SMS + Push alerts", "Real-time map tracking", "Custom schedule timing"],
            },
        ]

        self.stdout.write("\nSeeding Subscription Plans...")
        for plan_info in plans_data:
            plan, created = SubscriptionPlan.objects.get_or_create(
                name=plan_info["name"],
                defaults={
                    "monthly_cost": plan_info["monthly_cost"],
                    "max_children": plan_info["max_children"],
                    "priority_matching": plan_info["priority_matching"],
                    "features": plan_info["features"],
                    "is_active": True
                }
            )
            if created:
                self.stdout.write(self.style.SUCCESS(f"Created plan: {plan.name}"))
            else:
                self.stdout.write(self.style.WARNING(f"Plan {plan.name} already exists"))

        # 3. Seed Scheduled Reports
        reports_data = [
            {"report_type": ScheduledReport.BUSINESS_HEALTH, "frequency": ScheduledReport.DAILY},
            {"report_type": ScheduledReport.SAFETY_INCIDENTS, "frequency": ScheduledReport.DAILY},
            {"report_type": ScheduledReport.REVENUE_CHURN, "frequency": ScheduledReport.WEEKLY},
            {"report_type": ScheduledReport.DRIVER_PERFORMANCE, "frequency": ScheduledReport.WEEKLY},
        ]

        self.stdout.write("\nSeeding Scheduled Reports...")
        for report_info in reports_data:
            report, created = ScheduledReport.objects.get_or_create(
                report_type=report_info["report_type"],
                defaults={
                    "frequency": report_info["frequency"],
                    "recipients": ["admin@schoolrun.ng"],
                    "is_active": True
                }
            )
            if created:
                self.stdout.write(self.style.SUCCESS(f"Created report: {report.get_report_type_display()}"))
            else:
                self.stdout.write(self.style.WARNING(f"Report {report.get_report_type_display()} already exists"))

        self.stdout.write(self.style.SUCCESS("\nDatabase seeding completed!"))
