from datetime import timedelta

from django.core.paginator import Paginator
from django.db.models import Avg, Sum
from django.db.models.deletion import ProtectedError
from django.shortcuts import get_object_or_404
from django.utils import timezone
from rest_framework.response import Response
from rest_framework.views import APIView

from accounts.models import CustomUser, Driver, Notification, Parent, VerificationDocument
from children.models import Child
from incidents.models import Incident, IncidentTimeline
from main.firebase_push import notify, notify_admins
from payments.models import Subscription, Transaction
from trips.models import Assignment, LocationPing, Stop, Trip
from trips.tasks import sync_trip_for_schedule
from zones.models import Zone

from .admin_permissions import IsAdmin
from .admin_serializers import (
    REQUIRED_DOC_TYPES,
    serialize_driver_detail,
    serialize_driver_list_item,
    serialize_fleet_van,
    serialize_incident,
    serialize_incident_detail,
    serialize_parent_detail,
    serialize_parent_row,
    serialize_route,
    serialize_transaction,
    serialize_user_row,
    serialize_zone,
)

MANAGEABLE_ROLES = [CustomUser.Role.PARENT, CustomUser.Role.DRIVER]

PARENT_PAGE_SIZE = 20


def ok(data, status_code=200):
    return Response(data, status=status_code)


def err(detail, status_code=400):
    return Response({"detail": detail}, status=status_code)


class AdminOverviewView(APIView):
    permission_classes = [IsAdmin]

    def get(self, request):
        today = timezone.localdate()
        week_ago = today - timedelta(days=6)

        pending_drivers = Driver.objects.filter(is_verified=False).select_related("user")
        pending_parents = Parent.objects.filter(user__nin_verified=False).select_related("user")

        approvals = []
        for d in pending_drivers[:10]:
            approvals.append(
                {
                    "id": str(d.id),
                    "applicant_name": d.user.full_name or d.user.phone,
                    "applicant_type": "DRIVER",
                    "location": d.zone.name if d.zone else "Unassigned",
                    "submitted": d.created_at.date().isoformat(),
                    "status": "PENDING",
                    "documents": [
                        {"label": "License", "ok": d.documents.filter(doc_type=VerificationDocument.DocType.LICENSE).exists()},
                        {"label": "Inspection", "ok": d.documents.filter(doc_type=VerificationDocument.DocType.INSPECTION).exists()},
                        {"label": "Background Check", "ok": d.documents.filter(doc_type=VerificationDocument.DocType.BACKGROUND).exists()},
                    ],
                }
            )
        for p in pending_parents[:10]:
            approvals.append(
                {
                    "id": str(p.id),
                    "applicant_name": p.user.full_name or p.user.phone,
                    "applicant_type": "PARENT",
                    "location": p.zone.name if p.zone else "Unassigned",
                    "submitted": p.created_at.date().isoformat(),
                    "status": "PENDING",
                    "documents": [{"label": "NIN Verification", "ok": False}],
                }
            )

        weekly_trips = []
        for i in range(7):
            day = week_ago + timedelta(days=i)
            weekly_trips.append(
                {"label": day.strftime("%a"), "value": Trip.objects.filter(service_date=day).count()}
            )

        verified_drivers = Driver.objects.filter(is_verified=True)
        on_route_ids = Trip.objects.filter(
            service_date=today, status=Trip.Status.IN_PROGRESS
        ).values_list("driver_id", flat=True)
        on_route = verified_drivers.filter(id__in=on_route_ids).count()
        idle = verified_drivers.exclude(id__in=on_route_ids).count()

        recent_stops = Stop.objects.filter(picked_at__isnull=False).select_related(
            "child", "trip__driver__user"
        ).order_by("-picked_at")[:5]
        recent_txns = Transaction.objects.filter(status=Transaction.PAID).select_related(
            "parent__user"
        ).order_by("-processed_at")[:3]
        recent_incidents = Incident.objects.select_related("triggered_by").order_by("-created_at")[:3]

        activity = []
        for s in recent_stops:
            activity.append(
                {
                    "id": f"stop-{s.id}",
                    "icon": "check",
                    "title": f"{s.child.full_name} picked up",
                    "subtitle": f"{s.trip.driver.user.full_name} · {s.picked_at.strftime('%H:%M')}",
                    "_at": s.picked_at,
                }
            )
        for t in recent_txns:
            activity.append(
                {
                    "id": f"txn-{t.id}",
                    "icon": "payment",
                    "title": f"Payment received — {t.parent.user.full_name or t.parent.user.phone}",
                    "subtitle": f"₦{t.amount}",
                    "_at": t.processed_at,
                }
            )
        for i in recent_incidents:
            activity.append(
                {
                    "id": f"inc-{i.id}",
                    "icon": "panic" if i.severity == Incident.CRITICAL else "warning",
                    "title": i.get_incident_type_display(),
                    "subtitle": i.incident_id,
                    "_at": i.created_at,
                }
            )
        # Sort by actual event time, not the string id (which sorted by type
        # prefix — "txn-"/"stop-"/"inc-" — not chronological order at all).
        activity.sort(key=lambda a: a["_at"], reverse=True)
        for a in activity:
            del a["_at"]

        return ok(
            {
                "admin_name": request.user.full_name or request.user.phone,
                "date": today.isoformat(),
                "stats": {
                    "active_families": {"value": Parent.objects.count(), "trend_pct": 0},
                    "active_drivers": {"value": verified_drivers.count(), "trend_abs": 0},
                    "trips_today": {"value": Trip.objects.filter(service_date=today).count(), "trend_pct": 0},
                    "pending_approvals": {"value": len(approvals), "new_count": 0},
                },
                "weekly_trips": weekly_trips,
                "driver_status": [
                    {"label": "On Route", "value": on_route, "tone": "success"},
                    {"label": "Idle", "value": idle, "tone": "muted"},
                    {"label": "Pending Approval", "value": pending_drivers.count(), "tone": "orange"},
                ],
                "pending_approvals": approvals,
                "live_activity": activity[:8],
            }
        )


class AdminDriverListView(APIView):
    permission_classes = [IsAdmin]

    def get(self, request):
        drivers = Driver.objects.select_related("user", "zone").prefetch_related("documents").order_by("-created_at")
        bgc_in_progress = sum(
            1 for d in drivers if d.documents.filter(
                doc_type=VerificationDocument.DocType.BACKGROUND,
                status=VerificationDocument.Status.PENDING,
            ).exists()
        )
        rejected = VerificationDocument.objects.filter(status=VerificationDocument.Status.REJECTED).values(
            "driver"
        ).distinct().count()
        return ok(
            {
                "stats": {
                    "awaiting_review": drivers.filter(is_verified=False).count(),
                    "bgc_in_progress": bgc_in_progress,
                    "approved_drivers": drivers.filter(is_verified=True).count(),
                    "rejected_all_time": rejected,
                },
                "results": [serialize_driver_list_item(d) for d in drivers],
            }
        )

    def post(self, request):
        body = request.data
        phone = (body.get("phone") or "").replace(" ", "")
        vehicle = (body.get("vehicle") or "").strip()
        make, _, model = vehicle.partition(" ")
        zone = None
        zone_name = (body.get("zone") or "").strip()
        if zone_name and zone_name.lower() != "unassigned":
            zone = Zone.objects.filter(name__iexact=zone_name).first()

        if CustomUser.objects.filter(phone=phone).exists():
            return err("A user with this phone already exists.", 409)

        user = CustomUser.objects.create_user(
            phone=phone,
            password="password",
            full_name=body.get("full_name", ""),
            role=CustomUser.Role.DRIVER,
            push_notifications_enabled=True,
        )
        driver = Driver.objects.create(
            user=user,
            vehicle_make=make,
            vehicle_model=model,
            plate=body.get("plate", ""),
            zone=zone,
            driver_since=timezone.now().date(),
        )
        return ok(serialize_driver_detail(driver), 201)


class AdminDriverDetailView(APIView):
    permission_classes = [IsAdmin]

    def get(self, request, pk):
        driver = get_object_or_404(Driver.objects.select_related("user", "zone"), pk=pk)
        return ok(serialize_driver_detail(driver))


class AdminDriverApproveView(APIView):
    permission_classes = [IsAdmin]

    def post(self, request, pk):
        driver = get_object_or_404(Driver, pk=pk)
        driver.is_verified = True
        driver.save()
        return ok(serialize_driver_detail(driver))


class AdminDriverRejectView(APIView):
    permission_classes = [IsAdmin]

    def post(self, request, pk):
        driver = get_object_or_404(Driver, pk=pk)
        driver.is_verified = False
        driver.save()
        return ok(None, 204)


class AdminDriverRequestDocsView(APIView):
    permission_classes = [IsAdmin]

    def post(self, request, pk):
        driver = get_object_or_404(Driver, pk=pk)
        existing = {d.doc_type for d in driver.documents.all()}
        for doc_type in REQUIRED_DOC_TYPES:
            if doc_type not in existing:
                VerificationDocument.objects.create(driver=driver, doc_type=doc_type, status=VerificationDocument.Status.PENDING)
        return ok(serialize_driver_detail(driver))


class AdminParentListView(APIView):
    permission_classes = [IsAdmin]

    def get(self, request):
        parents = Parent.objects.select_related("user", "zone").prefetch_related("subscriptions", "children")
        pairs = [(p, serialize_parent_row(p)) for p in parents]

        q = (request.query_params.get("q") or "").strip().lower()
        if q:
            pairs = [
                (p, r) for p, r in pairs
                if q in r["full_name"].lower() or q in r["phone"].lower() or q in r["zone"].lower()
            ]

        status_filter = request.query_params.get("status")
        if status_filter:
            pairs = [(p, r) for p, r in pairs if r["account_status"].lower() == status_filter.lower()]

        zone_filter = request.query_params.get("zone")
        if zone_filter:
            pairs = [(p, r) for p, r in pairs if r["zone"].lower() == zone_filter.lower()]

        plan_filter = request.query_params.get("plan")
        if plan_filter:
            pairs = [(p, r) for p, r in pairs if r["plan"].lower() == plan_filter.lower()]

        ordering = request.query_params.get("ordering", "-created_at")
        if ordering == "created_at":
            pairs.sort(key=lambda pr: pr[0].created_at)
        elif ordering == "full_name":
            pairs.sort(key=lambda pr: pr[1]["full_name"].lower())
        else:
            pairs.sort(key=lambda pr: pr[0].created_at, reverse=True)

        count = len(pairs)
        page = max(int(request.query_params.get("page") or 1), 1)
        paginator = Paginator([r for _, r in pairs], PARENT_PAGE_SIZE)
        page_results = list(paginator.get_page(page).object_list)

        return ok(
            {
                "stats": {
                    "total_families": parents.count(),
                    "active_subscriptions": Subscription.objects.filter(status=Subscription.ACTIVE).count(),
                    "pending_verification": parents.filter(user__nin_verified=False).count(),
                    "overdue_payments": Subscription.objects.filter(status=Subscription.OVERDUE).count(),
                    "total_children": Child.objects.filter(is_active=True).count(),
                },
                "count": count,
                "results": page_results,
            }
        )

    def post(self, request):
        body = request.data
        phone = (body.get("phone") or "").replace(" ", "")
        if not phone:
            return err("phone is required.", 400)
        if CustomUser.objects.filter(phone=phone).exists():
            return err("A user with this phone already exists.", 409)

        zone = None
        zone_name = (body.get("zone") or "").strip()
        if zone_name and zone_name.lower() != "unassigned":
            zone = Zone.objects.filter(name__iexact=zone_name).first()

        user = CustomUser.objects.create_user(
            phone=phone,
            password="password",
            full_name=body.get("full_name", ""),
            role=CustomUser.Role.PARENT,
            push_notifications_enabled=True,
        )
        parent = Parent.objects.create(
            user=user,
            emergency_contact=body.get("emergency_contact", ""),
            zone=zone,
        )
        return ok(serialize_parent_row(parent), 201)


class AdminParentDetailView(APIView):
    permission_classes = [IsAdmin]

    def get(self, request, pk):
        parent = get_object_or_404(Parent.objects.select_related("user", "zone"), pk=pk)
        return ok(serialize_parent_detail(parent))


class AdminParentSuspendView(APIView):
    permission_classes = [IsAdmin]

    def post(self, request, pk):
        parent = get_object_or_404(Parent.objects.select_related("user"), pk=pk)
        parent.user.is_active = not parent.user.is_active
        parent.user.save()
        return ok(serialize_parent_row(parent))


class AdminParentVerifyNinView(APIView):
    permission_classes = [IsAdmin]

    def post(self, request, pk):
        parent = get_object_or_404(Parent.objects.select_related("user"), pk=pk)
        parent.user.nin_verified = True
        parent.user.save()
        notify(
            parent.user,
            Notification.Kind.SYSTEM,
            "ID verification approved",
            "Your identity verification is complete.",
        )
        return ok(serialize_parent_row(parent))


class AdminParentRejectNinView(APIView):
    permission_classes = [IsAdmin]

    def post(self, request, pk):
        parent = get_object_or_404(Parent.objects.select_related("user"), pk=pk)
        parent.user.nin_verified = False
        parent.user.save()
        notify(
            parent.user,
            Notification.Kind.SYSTEM,
            "ID verification rejected",
            "We couldn't verify your ID — please resubmit your NIN details.",
        )
        return ok(serialize_parent_row(parent))


class AdminParentAssignDriverView(APIView):
    permission_classes = [IsAdmin]

    def post(self, request, pk):
        parent = get_object_or_404(Parent, pk=pk)
        driver_id = request.data.get("driver_id")
        if not driver_id:
            return err("driver_id is required.", 400)
        driver = get_object_or_404(Driver, pk=driver_id)
        if not driver.is_verified:
            return err("Driver is not approved yet.", 400)

        Assignment.objects.filter(parent=parent, is_active=True).update(is_active=False)
        Assignment.objects.create(parent=parent, driver=driver, is_active=True)

        # Reflect the new assignment on the driver's manifest immediately for
        # any of the parent's children already scheduled for today, rather
        # than waiting on the next schedule save.
        for child in Child.objects.filter(parent=parent, is_active=True):
            sync_trip_for_schedule(child)

        return ok(serialize_parent_row(parent))


class AdminParentUnassignDriverView(APIView):
    permission_classes = [IsAdmin]

    def post(self, request, pk):
        parent = get_object_or_404(Parent, pk=pk)
        Assignment.objects.filter(parent=parent, is_active=True).update(is_active=False)
        return ok(serialize_parent_row(parent))


class AdminZoneListView(APIView):
    permission_classes = [IsAdmin]

    def get(self, request):
        zones = list(Zone.objects.filter(is_active=True).order_by("name"))
        today = timezone.localdate()
        active_trips = Trip.objects.filter(service_date=today, status=Trip.Status.IN_PROGRESS).select_related(
            "driver__user", "driver__zone"
        ).prefetch_related("stops__child")
        return ok(
            {
                "zones": [serialize_zone(z, i) for i, z in enumerate(zones)],
                "routes": {str(t.id): serialize_route(t) for t in active_trips},
            }
        )


class AdminDispatchView(APIView):
    permission_classes = [IsAdmin]

    def get(self, request):
        today = timezone.localdate()
        active_trips = list(
            Trip.objects.filter(service_date=today, status=Trip.Status.IN_PROGRESS).select_related(
                "driver__user"
            ).prefetch_related("stops__child")
        )
        active_driver_ids = [t.driver_id for t in active_trips]
        idle_drivers = Driver.objects.filter(is_verified=True).exclude(id__in=active_driver_ids).select_related("user")

        return ok(
            {
                "stats": {
                    "active_routes": len(active_trips),
                    "live_active": len(active_trips),
                    "idle": idle_drivers.count(),
                },
                "fleet": [serialize_fleet_van(t) for t in active_trips],
                "idle": [
                    {"id": str(d.id), "driver_name": d.user.full_name, "phone": d.user.phone, "plate": d.plate}
                    for d in idle_drivers
                ],
            }
        )


class AdminDriverTrailView(APIView):
    """Breadcrumb trail of a van's recent GPS fixes, for the Dispatch map's
    Track view. Defaults to the last 30 minutes, clamped to the trip's own
    start so it never bleeds in fixes from an earlier trip that day."""
    permission_classes = [IsAdmin]

    def get(self, request, trip_id):
        trip = get_object_or_404(Trip, id=trip_id)
        minutes = int(request.query_params.get("minutes", 30))
        since = timezone.now() - timedelta(minutes=minutes)
        if trip.started_at and trip.started_at > since:
            since = trip.started_at

        pings = LocationPing.objects.filter(driver=trip.driver, created_at__gte=since).order_by("created_at")
        return ok(
            {
                "points": [
                    {"lat": p.point.y, "lng": p.point.x, "at": p.created_at.isoformat()} for p in pings
                ]
            }
        )


class AdminEmergencyDispatchView(APIView):
    permission_classes = [IsAdmin]

    def post(self, request):
        trip_id = request.data.get("trip_id")
        trip = get_object_or_404(Trip, id=trip_id, status=Trip.Status.IN_PROGRESS)

        incident = Incident.objects.create(
            incident_id=Incident.next_incident_id(),
            incident_type=Incident.PANIC_ALERT,
            severity=Incident.CRITICAL,
            status=Incident.OPEN,
            triggered_by=request.user,
            trip=trip,
        )
        IncidentTimeline.objects.create(
            incident=incident,
            actor=request.user,
            event_text=f"Emergency dispatch triggered by {request.user.full_name} for {trip.driver.user.full_name}'s van.",
        )

        title = "Emergency dispatch triggered"
        subtitle = f"{trip.driver.user.full_name} · {incident.incident_id}"
        notify_admins(
            Notification.Kind.SYSTEM,
            title,
            subtitle,
            {
                "kind": "ADMIN_ACTIVITY",
                "icon": "panic",
                "activity_id": f"incident-{incident.id}",
                "title": title,
                "subtitle": subtitle,
            },
        )

        return ok(serialize_incident_detail(incident), 201)


class AdminPaymentsView(APIView):
    permission_classes = [IsAdmin]

    def get(self, request):
        active_subs = Subscription.objects.filter(status=Subscription.ACTIVE).select_related("plan")
        mrr = sum((s.plan.monthly_cost for s in active_subs if s.plan), 0) if active_subs else 0
        overdue_subs = Subscription.objects.filter(status=Subscription.OVERDUE).select_related("plan", "parent__user")
        overdue_balance = sum((s.plan.monthly_cost for s in overdue_subs if s.plan), 0)

        today = timezone.localdate()
        # Build last 6 calendar months explicitly (avoids month-arithmetic edge cases)
        months = []
        y, m = today.year, today.month
        for _ in range(6):
            months.append((y, m))
            m -= 1
            if m == 0:
                m = 12
                y -= 1
        months.reverse()
        monthly_revenue = []
        for y, m in months:
            total = Transaction.objects.filter(
                status=Transaction.PAID, processed_at__year=y, processed_at__month=m
            ).aggregate(total=Sum("amount"))["total"] or 0
            monthly_revenue.append({"label": f"{y}-{m:02d}", "value": float(total)})

        plan_counts = {"STANDARD": 0, "PREMIUM": 0, "FAMILY_PLUS": 0}
        for s in active_subs:
            if not s.plan:
                continue
            name = s.plan.name.lower()
            key = "FAMILY_PLUS" if "family" in name else "PREMIUM" if "premium" in name else "STANDARD"
            plan_counts[key] += 1

        pending_refunds = Transaction.objects.filter(payment_type=Transaction.REFUND, status=Transaction.PENDING)

        overdue_list = []
        for s in overdue_subs:
            days_overdue = (today - s.next_billing_date).days if s.next_billing_date else 0
            overdue_list.append(
                {
                    "id": str(s.id),
                    "name": s.parent.user.full_name or s.parent.user.phone,
                    "amount": float(s.plan.monthly_cost) if s.plan else 0,
                    "days_overdue": max(days_overdue, 0),
                }
            )

        transactions = Transaction.objects.select_related("parent__user").order_by("-processed_at")[:50]

        return ok(
            {
                "overview": {
                    "mrr": float(mrr),
                    "mrr_trend_pct": 0,
                    "arr_projected": float(mrr) * 12,
                    "arr_trend_pct": 0,
                    "overdue_balance": float(overdue_balance),
                    "overdue_accounts": overdue_subs.count(),
                    "pending_refunds": pending_refunds.count(),
                    "pending_refunds_open": pending_refunds.count(),
                    "monthly_revenue": monthly_revenue,
                    "plan_distribution": [
                        {"label": "Standard", "value": plan_counts["STANDARD"], "tone": "blue"},
                        {"label": "Premium", "value": plan_counts["PREMIUM"], "tone": "orange"},
                        {"label": "Family+", "value": plan_counts["FAMILY_PLUS"], "tone": "success"},
                    ],
                    "overdue_list": overdue_list,
                },
                "transactions": [serialize_transaction(t) for t in transactions],
            }
        )


class AdminRefundTransactionView(APIView):
    permission_classes = [IsAdmin]

    def post(self, request, pk):
        txn = get_object_or_404(Transaction, pk=pk)
        txn.status = Transaction.REFUNDED
        txn.processed_at = timezone.now()
        txn.save()
        return ok(serialize_transaction(txn))


class AdminIncidentListView(APIView):
    permission_classes = [IsAdmin]

    def get(self, request):
        incidents = Incident.objects.select_related("triggered_by", "trip__driver__user", "child").order_by(
            "-created_at"
        )
        week_ago = timezone.now() - timedelta(days=7)
        month_start = timezone.localdate().replace(day=1)
        resolved = incidents.filter(status=Incident.RESOLVED)
        avg_resolution = resolved.aggregate(avg=Avg("response_time"))["avg"]

        return ok(
            {
                "stats": {
                    "open_incidents": incidents.exclude(status=Incident.RESOLVED).count(),
                    "route_deviations_7d": incidents.filter(
                        incident_type=Incident.ROUTE_DEVIATION, created_at__gte=week_ago
                    ).count(),
                    "resolved_this_month": resolved.filter(resolved_at__gte=month_start).count(),
                    "avg_resolution_min": round(avg_resolution.total_seconds() / 60) if avg_resolution else 0,
                },
                "results": [serialize_incident(i) for i in incidents],
            }
        )


class AdminIncidentResolveView(APIView):
    permission_classes = [IsAdmin]

    def post(self, request, incident_id):
        incident = get_object_or_404(Incident, incident_id=incident_id)
        incident.status = Incident.RESOLVED
        incident.resolved_at = timezone.now()
        incident.save()
        IncidentTimeline.objects.create(
            incident=incident, actor=request.user, event_text=f"Marked resolved by {request.user.full_name}"
        )
        return ok(serialize_incident_detail(incident))


class AdminAnalyticsView(APIView):
    permission_classes = [IsAdmin]

    def get(self, request):
        today = timezone.localdate()
        month_start = today.replace(day=1)

        total_trips = Trip.objects.count()
        completed_trips = Trip.objects.filter(status=Trip.Status.COMPLETED).count()
        safe_completion_pct = round((completed_trips / total_trips) * 100) if total_trips else 0

        avg_rating = Driver.objects.filter(is_verified=True).aggregate(avg=Avg("rating"))["avg"] or 0

        months = []
        y, m = today.year, today.month
        for _ in range(6):
            months.append((y, m))
            m -= 1
            if m == 0:
                m = 12
                y -= 1
        months.reverse()
        family_growth = []
        for y, m in months:
            count = Parent.objects.filter(created_at__year=y, created_at__month=m).count()
            family_growth.append({"label": f"{y}-{m:02d}", "families": count})

        zones = Zone.objects.filter(is_active=True)
        on_time_by_zone = []
        for z in zones:
            zone_trips = Trip.objects.filter(driver__zone=z)
            zt_total = zone_trips.count()
            zt_done = zone_trips.filter(status=Trip.Status.COMPLETED).count()
            on_time_by_zone.append(
                {"zone": z.name, "pct": round((zt_done / zt_total) * 100) if zt_total else 0}
            )

        leaderboard = []
        for rank, d in enumerate(
            Driver.objects.filter(is_verified=True).select_related("user", "zone").order_by("-rating")[:10], start=1
        ):
            trips = d.trips.count()
            done = d.trips.filter(status=Trip.Status.COMPLETED).count()
            leaderboard.append(
                {
                    "rank": rank,
                    "full_name": d.user.full_name,
                    "zone": d.zone.name if d.zone else "Unassigned",
                    "trips": trips,
                    "rating": float(d.rating),
                    "on_time_pct": round((done / trips) * 100) if trips else 0,
                    "incidents": Incident.objects.filter(trip__driver=d).count(),
                    "status": "TOP_DRIVER" if rank == 1 else "ACTIVE",
                }
            )

        active_subs = Subscription.objects.filter(status=Subscription.ACTIVE).count()
        cancelled_subs = Subscription.objects.filter(status=Subscription.CANCELLED).count()
        total_subs = active_subs + cancelled_subs
        retention_pct = round((active_subs / total_subs) * 100) if total_subs else 100
        churn_pct = 100 - retention_pct

        return ok(
            {
                "new_families": {"value": Parent.objects.filter(created_at__gte=month_start).count(), "trend_pct": 0},
                "total_trips": {"value": total_trips, "trend_pct": 0},
                "avg_rating": {"value": round(float(avg_rating), 2), "trend_abs": 0},
                "safe_completion_pct": {"value": safe_completion_pct, "trend_pct": 0},
                "family_growth": family_growth,
                "on_time_by_zone": on_time_by_zone,
                "driver_leaderboard": leaderboard,
                "retention_pct": retention_pct,
                "churn_pct": churn_pct,
                "new_this_month": Parent.objects.filter(created_at__gte=month_start).count(),
                "churned_this_month": Subscription.objects.filter(
                    status=Subscription.CANCELLED, updated_at__gte=month_start
                ).count(),
            }
        )


class AdminUserListView(APIView):
    """Account management for parent/driver logins: view, set password,
    delete. Distinct from AdminParentListView/AdminDriverListView, which
    manage the business-facing profile (subscriptions, docs, assignment)
    rather than the underlying login credentials."""
    permission_classes = [IsAdmin]

    def get(self, request):
        users = CustomUser.objects.filter(role__in=MANAGEABLE_ROLES).select_related(
            "parent__zone", "driver__zone"
        ).order_by("-id")
        rows = [serialize_user_row(u) for u in users]

        role_filter = (request.query_params.get("role") or "").strip().upper()
        if role_filter in MANAGEABLE_ROLES:
            rows = [r for r in rows if r["role"] == role_filter]

        q = (request.query_params.get("q") or "").strip().lower()
        if q:
            rows = [r for r in rows if q in r["full_name"].lower() or q in (r["phone"] or "").lower()]

        return ok({"count": len(rows), "results": rows})


class AdminUserSetPasswordView(APIView):
    permission_classes = [IsAdmin]

    def post(self, request, pk):
        user = get_object_or_404(CustomUser, pk=pk, role__in=MANAGEABLE_ROLES)
        password = (request.data.get("password") or "").strip()
        if len(password) < 6:
            return err("Password must be at least 6 characters.", 400)
        user.set_password(password)
        user.save(update_fields=["password"])
        return ok({"id": str(user.id)})


class AdminUserDeleteView(APIView):
    permission_classes = [IsAdmin]

    def delete(self, request, pk):
        user = get_object_or_404(CustomUser, pk=pk, role__in=MANAGEABLE_ROLES)
        try:
            user.delete()
        except ProtectedError:
            if user.role == CustomUser.Role.DRIVER:
                detail = (
                    "Can't delete this driver — they have trips or assignments on record. "
                    "Reassign or clear those first."
                )
            else:
                detail = (
                    "Can't delete this parent — their children have pickup/dropoff history on "
                    "record, which can't be removed. Deactivate the account instead."
                )
            return err(detail, 409)
        return ok(None, 204)
