from datetime import timedelta
from math import radians, sin, cos, sqrt, asin

from django.db import transaction
from django.db.models import Prefetch
from django.utils import timezone
from django.shortcuts import get_object_or_404
from rest_framework import status
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework_simplejwt.tokens import RefreshToken
from rest_framework_simplejwt.views import TokenRefreshView

from .admin_permissions import IsAdmin

from accounts.models import CustomUser, Parent, Driver, Notification, Device
from children.models import Child, School, Schedule
from trips.models import Trip, Stop, Assignment, LocationPing
from trips.tasks import sync_trip_for_schedule
from incidents.models import Incident, IncidentTimeline

from main.firebase_push import notify, notify_admins

from .serializers import (
    RegisterSerializer,
    LoginSerializer,
    GoogleLoginSerializer,
    MeSerializer,
    MePatchSerializer,
    MeChangePasswordSerializer,
    SchoolSerializer,
    ChildListSerializer,
    ChildCreateSerializer,
    SchedulePutSerializer,
    DashboardSerializer,
    ParentDriverSerializer,
    ManifestSerializer,
    ManifestTripSerializer,
    StopEventSerializer,
    DriverLocationPingSerializer,
    StopNoShowSerializer,
    StopEventResultSerializer,
    StopDetailSerializer,
    IncidentReportSerializer,
    HistoryRowSerializer,
    NotificationSerializer,
    NotificationsReadSerializer,
    DeviceSerializer,
    today_date,
)


def haversine(lat1, lng1, lat2, lng2):
    R = 6_371_000
    dlat = radians(lat2 - lat1)
    dlng = radians(lng2 - lng1)
    a = sin(dlat / 2) ** 2 + cos(radians(lat1)) * cos(radians(lat2)) * sin(dlng / 2) ** 2
    return 2 * R * asin(sqrt(a))


def ok(data, status_code=200):
    return Response(data, status=status_code)


def err(detail, status_code=400):
    return Response({'detail': detail}, status=status_code)


class RegisterView(APIView):
    permission_classes = [AllowAny]

    def post(self, request):
        serializer = RegisterSerializer(data=request.data)
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
        user = serializer.save()
        tokens = user.tokens()
        return Response({
            'access': tokens['access'],
            'refresh': tokens['refresh'],
            'user': {
                'id': user.id,
                'role': user.role,
                'full_name': user.full_name,
                'phone': user.phone,
            },
        }, status=status.HTTP_201_CREATED)


class LoginView(APIView):
    permission_classes = [AllowAny]

    def post(self, request):
        serializer = LoginSerializer(data=request.data)
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_401_UNAUTHORIZED)
        user = serializer.validated_data['user']
        tokens = user.tokens()
        return Response({
            'access': tokens['access'],
            'refresh': tokens['refresh'],
            'user': {
                'id': user.id,
                'role': user.role,
                'full_name': user.full_name,
                'phone': user.phone,
                'is_super_admin': user.is_superuser,
                'must_change_password': user.must_change_password,
            },
        })


class GoogleLoginView(APIView):
    permission_classes = [AllowAny]

    def post(self, request):
        serializer = GoogleLoginSerializer(data=request.data)
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_401_UNAUTHORIZED)
        user = serializer.validated_data['user']
        tokens = user.tokens()
        return Response({
            'access': tokens['access'],
            'refresh': tokens['refresh'],
            'user': {
                'id': user.id,
                'role': user.role,
                'full_name': user.full_name,
                'phone': user.phone,
                'is_super_admin': user.is_superuser,
                'must_change_password': user.must_change_password,
            },
        })


class MeView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        serializer = MeSerializer(request.user)
        return ok(serializer.data)

    def patch(self, request):
        serializer = MePatchSerializer(data=request.data, context={'request': request})
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
        data = serializer.validated_data
        if 'full_name' in data:
            request.user.full_name = data['full_name']
        if 'phone' in data:
            request.user.phone = data['phone']
        if 'preferences' in data:
            prefs = data['preferences']
            if 'push' in prefs:
                if request.user.role == CustomUser.Role.DRIVER:
                    request.user.push_notifications_enabled = True
                else:
                    request.user.push_notifications_enabled = prefs['push']
            if 'location_sharing' in prefs:
                request.user.location_sharing_enabled = prefs['location_sharing']
            if 'dark_mode' in prefs:
                request.user.dark_mode = prefs['dark_mode']
        request.user.save()
        return ok(MeSerializer(request.user).data)


class MeChangePasswordView(APIView):
    """Self-service password change. The one write endpoint a
    must_change_password user can still reach (see
    accounts.middleware.ForcePasswordChangeMiddleware) — clearing the flag
    here is what lets them back into the rest of the API."""
    permission_classes = [IsAuthenticated]

    def post(self, request):
        serializer = MeChangePasswordSerializer(data=request.data, context={'request': request})
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
        request.user.set_password(serializer.validated_data['new_password'])
        request.user.must_change_password = False
        request.user.save(update_fields=['password', 'must_change_password'])
        return ok(None)


class SchoolListView(APIView):
    def get_permissions(self):
        if self.request.method == 'POST':
            return [IsAdmin()]
        return [IsAuthenticated()]

    def get(self, request):
        q = request.query_params.get('q', '')
        schools = School.objects.all()
        if q:
            schools = schools.filter(name__icontains=q)
        serializer = SchoolSerializer(schools, many=True)
        return ok(serializer.data)

    def post(self, request):
        serializer = SchoolSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        serializer.save()
        return ok(serializer.data, status_code=201)


class ChildListCreateView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        try:
            parent = Parent.objects.get(user=request.user)
        except Parent.DoesNotExist:
            return err('Only parents can manage children.', 403)
        children = Child.objects.filter(parent=parent, is_active=True)
        serializer = ChildListSerializer(children, many=True)
        return ok(serializer.data)

    def post(self, request):
        try:
            Parent.objects.get(user=request.user)
        except Parent.DoesNotExist:
            return err('Only parents can create children.', 403)
        serializer = ChildCreateSerializer(
            data=request.data,
            context={'request': request},
        )
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
        child = serializer.save()
        return ok(ChildListSerializer(child).data, status.HTTP_201_CREATED)


class ChildDetailView(APIView):
    permission_classes = [IsAuthenticated]

    def get_child(self, request, pk):
        try:
            parent = Parent.objects.get(user=request.user)
        except Parent.DoesNotExist:
            return None
        return get_object_or_404(Child, id=pk, parent=parent)

    def get(self, request, pk):
        child = self.get_child(request, pk)
        if not child:
            return err('Only parents can access children.', 403)
        return ok(ChildListSerializer(child).data)

    def patch(self, request, pk):
        try:
            parent = Parent.objects.get(user=request.user)
        except Parent.DoesNotExist:
            return err('Only parents can update children.', 403)
        child = get_object_or_404(Child, id=pk, parent=parent)
        serializer = ChildCreateSerializer(
            child,
            data=request.data,
            partial=True,
            context={'request': request},
        )
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
        updated = serializer.save()
        return ok(ChildListSerializer(updated).data)

    def delete(self, request, pk):
        try:
            parent = Parent.objects.get(user=request.user)
        except Parent.DoesNotExist:
            return err('Only parents can delete children.', 403)
        child = get_object_or_404(Child, id=pk, parent=parent)
        child.is_active = False
        child.save()
        return Response(None, status=status.HTTP_204_NO_CONTENT)


class ChildScheduleView(APIView):
    permission_classes = [IsAuthenticated]

    def put(self, request, pk):
        try:
            parent = Parent.objects.get(user=request.user)
        except Parent.DoesNotExist:
            return err('Only parents can set schedules.', 403)
        child = get_object_or_404(Child, id=pk, parent=parent)
        serializer = SchedulePutSerializer(data=request.data)
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
        data = serializer.validated_data
        schedule, _ = Schedule.objects.update_or_create(
            child=child,
            defaults=data,
        )
        sync_trip_for_schedule(child)
        return ok({
            'morning_time': schedule.morning_time.strftime('%H:%M'),
            'afternoon_time': schedule.afternoon_time.strftime('%H:%M'),
            'days': schedule.days,
        })


class DashboardView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        try:
            parent = Parent.objects.get(user=request.user)
        except Parent.DoesNotExist:
            return err('Only parents can view dashboard.', 403)
        children = list(Child.objects.filter(parent=parent, is_active=True))
        # There's no Celery beat/worker deployed to run generate_daily_manifests
        # on a nightly cron (see trips/tasks.py), so today's trip/stops never
        # materialized on their own — only ChildScheduleView.put triggered
        # this, which is why the schedule looked "stuck" until a parent
        # re-saved it. Lazily ensure today's trip exists on every dashboard
        # load instead of waiting on infra that isn't running.
        for child in children:
            sync_trip_for_schedule(child)
        serializer = DashboardSerializer({'children': children})
        return ok(serializer.data)


class ParentDriverView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        try:
            parent = Parent.objects.get(user=request.user)
        except Parent.DoesNotExist:
            return err('Only parents can view driver info.', 403)
        assignment = Assignment.objects.filter(parent=parent, is_active=True).select_related('driver').first()
        if not assignment:
            return err('No driver assigned.', 404)
        serializer = ParentDriverSerializer(assignment.driver)
        return ok(serializer.data)


class DriverManifestView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        if request.user.role != CustomUser.Role.DRIVER:
            return err('Only drivers can view manifest.', 403)
        try:
            driver = Driver.objects.get(user=request.user)
        except Driver.DoesNotExist:
            return err('Driver profile not found.', 404)
        d = request.query_params.get('date', today_date().isoformat())
        if d == today_date().isoformat():
            # Same lazy materialization as DashboardView — covers a driver
            # opening their manifest before any parent has opened the
            # dashboard yet today.
            parent_ids = Assignment.objects.filter(
                driver=driver, is_active=True
            ).values_list('parent_id', flat=True)
            for child in Child.objects.filter(parent_id__in=parent_ids, is_active=True):
                sync_trip_for_schedule(child)
        trips = Trip.objects.filter(driver=driver, service_date=d).prefetch_related('stops__child')
        serializer = ManifestSerializer({'trips': list(trips)})
        return ok(serializer.data)


class TripStartView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request, pk):
        if request.user.role != CustomUser.Role.DRIVER:
            return err('Only drivers can start trips.', 403)
        trip = get_object_or_404(Trip, id=pk, driver__user=request.user)
        if trip.status != Trip.Status.SCHEDULED:
            return err(f'Trip is already {trip.status}.', 409)
        trip.status = Trip.Status.IN_PROGRESS
        trip.save()
        first_stop = trip.stops.filter(sequence=1).first()
        if first_stop and first_stop.status == Stop.Status.UPCOMING:
            first_stop.status = Stop.Status.NEXT
            first_stop.save()
        return ok({
            'id': str(trip.id),
            'direction': trip.direction,
            'status': trip.status,
        })


class TripCompleteView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request, pk):
        if request.user.role != CustomUser.Role.DRIVER:
            return err('Only drivers can complete trips.', 403)
        trip = get_object_or_404(Trip, id=pk, driver__user=request.user)
        if trip.status != Trip.Status.IN_PROGRESS:
            return err(f'Trip is {trip.status}, not in progress.', 409)
        trip.status = Trip.Status.COMPLETED
        trip.save()
        return ok({
            'id': str(trip.id),
            'direction': trip.direction,
            'status': trip.status,
        })


class DriverLocationPingView(APIView):
    """Foreground-only location ping sent by the driver's nav screen while a
    trip is in progress — powers the admin dispatch map's live van position.
    """
    permission_classes = [IsAuthenticated]

    def post(self, request):
        if request.user.role != CustomUser.Role.DRIVER:
            return err('Only drivers can send location pings.', 403)
        serializer = DriverLocationPingSerializer(data=request.data)
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
        data = serializer.validated_data
        from main.gis_fallback import GeoPoint
        driver = request.user.driver
        point = GeoPoint(data['lng'], data['lat'])
        driver.last_point = point
        driver.last_seen_at = timezone.now()
        driver.save(update_fields=['last_point', 'last_seen_at'])
        LocationPing.objects.create(driver=driver, point=point)
        # Trail only ever needs the last hour — prune older fixes on write
        # rather than running a separate cleanup job.
        LocationPing.objects.filter(
            driver=driver, created_at__lt=timezone.now() - timedelta(hours=1)
        ).delete()
        return Response(None, status=status.HTTP_204_NO_CONTENT)


GPS_TOLERANCE_M = 100


def process_stop_event(request, stop_id, kind):
    if request.user.role != CustomUser.Role.DRIVER:
        return err('Only drivers can update stops.', 403)
    stop = get_object_or_404(Stop, id=stop_id, trip__driver__user=request.user)
    trip = stop.trip

    if kind == 'no-show':
        serializer = StopNoShowSerializer(data=request.data)
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
        reason = serializer.validated_data['reason']
        stop.status = Stop.Status.NO_SHOW
        stop.save()

        notify(
            stop.child.parent.user,
            Notification.Kind.SYSTEM,
            f'{stop.child.full_name} marked as no-show',
            f'{request.user.full_name} could not complete the stop for {stop.child.full_name}: {reason}',
            {'kind': 'NO_SHOW', 'stop_id': str(stop.id)},
        )

        # A no-show can't just sit in the parent's notification feed — ops
        # needs to know a child wasn't collected while there's still time to
        # act, so it's escalated the same way an admin-triggered emergency
        # dispatch is (see AdminEmergencyDispatchView).
        incident = Incident.objects.create(
            incident_id=Incident.next_incident_id(),
            incident_type=Incident.NO_SHOW,
            severity=Incident.MEDIUM,
            status=Incident.OPEN,
            triggered_by=request.user,
            trip=trip,
            child=stop.child,
        )
        IncidentTimeline.objects.create(
            incident=incident,
            actor=request.user,
            event_text=f'No-show reported by {request.user.full_name}: {reason}',
        )
        admin_title = 'No-show reported'
        admin_subtitle = f'{stop.child.full_name} · {incident.incident_id}'
        notify_admins(
            Notification.Kind.SYSTEM,
            admin_title,
            admin_subtitle,
            {
                'kind': 'ADMIN_ACTIVITY',
                'icon': 'warning',
                'activity_id': f'incident-{incident.id}',
                'title': admin_title,
                'subtitle': admin_subtitle,
            },
        )
    else:
        serializer = StopEventSerializer(data=request.data)
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
        data = serializer.validated_data
        point = None
        gps_verified = None
        distance_m = None
        if data.get('lat') is not None and data.get('lng') is not None:
            from main.gis_fallback import GeoPoint
            point = GeoPoint(data['lng'], data['lat'])
            target = stop.child.pickup_point
            if target:
                distance_m = round(haversine(data['lat'], data['lng'], float(target.y), float(target.x)))
                gps_verified = distance_m <= GPS_TOLERANCE_M
            else:
                gps_verified = None
        if kind == 'pickup':
            stop.status = Stop.Status.PICKED_UP
            stop.picked_at = timezone.now()
            stop.picked_point = point
            notif_kind = Notification.Kind.PICKUP
            notif_title = f'{stop.child.full_name} picked up'
            notif_body = f'{stop.child.full_name} was collected by {request.user.full_name}.'
        else:
            stop.status = Stop.Status.DROPPED
            stop.dropped_at = timezone.now()
            stop.dropped_point = point
            if trip.direction == Trip.Direction.TO_SCHOOL:
                notif_kind = Notification.Kind.ARRIVAL
                notif_title = f'{stop.child.full_name} arrived at school'
                notif_body = f'{stop.child.full_name} was dropped at school by {request.user.full_name}.'
            else:
                notif_kind = Notification.Kind.DROPOFF
                notif_title = f'{stop.child.full_name} dropped off'
                notif_body = f'{stop.child.full_name} was dropped at home by {request.user.full_name}.'
        # COMPLETED is included alongside SCHEDULED because a trip can be
        # reopened by a stop added after it finished (see
        # sync_trip_for_schedule) — without this, a pickup/dropoff on that
        # late stop leaves the trip stuck at COMPLETED and it silently drops
        # off the admin dispatch view, which only shows IN_PROGRESS trips.
        if trip.status in (Trip.Status.SCHEDULED, Trip.Status.COMPLETED):
            trip.status = Trip.Status.IN_PROGRESS
            trip.save()
        stop.save()

        notify(
            stop.child.parent.user,
            notif_kind,
            notif_title,
            notif_body,
            {'kind': notif_kind, 'stop_id': str(stop.id)},
            stop=stop,
        )

        if kind == 'pickup':
            # Feeds the admin Overview's Live Activity panel in real time —
            # the payload carries everything the panel needs to render the
            # row, so the admin's browser never has to re-query the DB.
            notify_admins(
                Notification.Kind.SYSTEM,
                notif_title,
                notif_body,
                {
                    'kind': 'ADMIN_ACTIVITY',
                    'icon': 'check',
                    'activity_id': f'stop-{stop.id}',
                    'title': notif_title,
                    'subtitle': f'{request.user.full_name} · {stop.picked_at.strftime("%H:%M")}',
                },
            )

    next_stop = Stop.objects.filter(trip=trip, sequence__gt=stop.sequence, status=Stop.Status.UPCOMING).order_by('sequence').first()
    if next_stop:
        next_stop.status = Stop.Status.NEXT
        next_stop.save()
    elif not trip.stops.exclude(status__in=[Stop.Status.DROPPED, Stop.Status.NO_SHOW]).exists():
        # Every stop is resolved and nothing about this route is a pending
        # UI action — nothing else in the app ever calls TripCompleteView, so
        # without this a trip sits at IN_PROGRESS forever and never shows up
        # in the parent's trip history (which filters on status=COMPLETED).
        trip.status = Trip.Status.COMPLETED
        trip.save()

    result_data = {
        'stop': stop,
        'gps_verified': gps_verified if kind != 'no-show' else None,
        'distance_m': distance_m if kind != 'no-show' else None,
        'next_stop': next_stop,
    }
    serializer_result = StopEventResultSerializer(result_data)
    return ok(serializer_result.data)


class StopDetailView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request, pk):
        try:
            parent = Parent.objects.get(user=request.user)
        except Parent.DoesNotExist:
            return err('Only parents can view stop details.', 403)
        stop = get_object_or_404(
            Stop.objects.select_related('trip__driver__user', 'child__school'),
            id=pk,
            child__parent=parent,
        )
        return ok(StopDetailSerializer(stop).data)


class StopPickupView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request, pk):
        return process_stop_event(request, pk, 'pickup')


class StopDropoffView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request, pk):
        return process_stop_event(request, pk, 'dropoff')


class StopNoShowView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request, pk):
        return process_stop_event(request, pk, 'no-show')


INCIDENT_TYPE_FROM_CONTRACT = {
    'SICK_CHILD': Incident.SICK_CHILD,
    'ROUTE_DEVIATION': Incident.ROUTE_DEVIATION,
    'OTHER': Incident.OTHER,
}


class IncidentReportView(APIView):
    """Lets a driver or parent flag a problem outside the no-show flow (e.g.
    a sick child, a blocked route, a wrong pickup point) — the Trust & Safety
    screens' non-panic escalation path. Panic itself stays deferred (Phase 3);
    this never accepts `panic_alert` so a self-report can't impersonate one."""
    permission_classes = [IsAuthenticated]

    def post(self, request):
        serializer = IncidentReportSerializer(data=request.data)
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
        data = serializer.validated_data

        trip = None
        if data.get('trip_id'):
            trip_qs = Trip.objects.all()
            if request.user.role == CustomUser.Role.DRIVER:
                trip_qs = trip_qs.filter(driver__user=request.user)
            trip = get_object_or_404(trip_qs, id=data['trip_id'])

        child = None
        if data.get('child_id'):
            child_qs = Child.objects.all()
            if request.user.role == CustomUser.Role.PARENT:
                child_qs = child_qs.filter(parent__user=request.user)
            child = get_object_or_404(child_qs, id=data['child_id'])

        incident = Incident.objects.create(
            incident_id=Incident.next_incident_id(),
            incident_type=INCIDENT_TYPE_FROM_CONTRACT[data['incident_type']],
            severity=Incident.MEDIUM,
            status=Incident.OPEN,
            triggered_by=request.user,
            trip=trip,
            child=child,
        )
        who = request.user.full_name or request.user.phone
        IncidentTimeline.objects.create(
            incident=incident,
            actor=request.user,
            event_text=f'Reported by {who}: {data["description"]}',
        )
        admin_title = 'New incident reported'
        admin_subtitle = f'{who} · {incident.incident_id}'
        notify_admins(
            Notification.Kind.SYSTEM,
            admin_title,
            admin_subtitle,
            {
                'kind': 'ADMIN_ACTIVITY',
                'icon': 'warning',
                'activity_id': f'incident-{incident.id}',
                'title': admin_title,
                'subtitle': admin_subtitle,
            },
        )
        return ok({'id': incident.incident_id, 'status': incident.status}, status.HTTP_201_CREATED)


class HistoryView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        try:
            parent = Parent.objects.get(user=request.user)
        except Parent.DoesNotExist:
            return err('Only parents can view history.', 403)
        t = request.query_params.get('type', 'all')
        # A stop belongs in history once THAT child's leg is resolved — not
        # once the whole trip's status flips to COMPLETED, which only
        # happens after every stop on the route is resolved. On a shared
        # route, other stops can belong to other families, so gating on
        # Trip.status left a parent's history empty indefinitely even after
        # their own child was picked up and dropped off.
        stops = Stop.objects.filter(
            child__parent=parent,
            status__in=[Stop.Status.DROPPED, Stop.Status.NO_SHOW],
        ).select_related('trip', 'trip__driver__user', 'child', 'child__school').order_by('-updated_at')[:50]
        history = []
        for stop in stops:
            trip = stop.trip
            history.append({
                'id': stop.id,
                'type': 'RIDE',
                'at': stop.dropped_at or stop.picked_at or stop.updated_at,
                'title': f'{stop.child.full_name} — {"School" if trip.direction == "TO_SCHOOL" else "Home"}',
                'subtitle': f'{trip.driver.user.full_name} · {trip.driver.plate} · {stop.child.school.name}',
                'amount': None,
                'label': 'Completed' if stop.status == Stop.Status.DROPPED else 'No-show',
            })
        # PAYMENT/EMERGENCY rows don't exist yet (Phase 3/4 stubs — see
        # HistoryRow's type union) so those tabs correctly render empty for
        # now; the bug this fixes was falling through to "no filter" for any
        # `t` other than 'rides', so Payments/Emergency showed every ride.
        TYPE_FOR_TAB = {'rides': 'RIDE', 'payments': 'PAYMENT', 'emergency': 'EMERGENCY'}
        if t in TYPE_FOR_TAB:
            history = [h for h in history if h['type'] == TYPE_FOR_TAB[t]]
        return ok({
            'count': len(history),
            'next': None,
            'previous': None,
            'results': history,
        })


class NotificationListView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        unread = request.query_params.get('unread') == 'true'
        notifications = Notification.objects.filter(recipient=request.user)
        if unread:
            notifications = notifications.filter(is_read=False)
        notifications = notifications.order_by('-created_at')
        serializer = NotificationSerializer(notifications, many=True)
        return ok({
            'count': notifications.count(),
            'next': None,
            'previous': None,
            'results': serializer.data,
        })

    def delete(self, request):
        Notification.objects.filter(recipient=request.user).delete()
        return Response(None, status=status.HTTP_204_NO_CONTENT)


class NotificationDetailView(APIView):
    permission_classes = [IsAuthenticated]

    def delete(self, request, pk):
        get_object_or_404(Notification, id=pk, recipient=request.user).delete()
        return Response(None, status=status.HTTP_204_NO_CONTENT)


class NotificationReadView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        serializer = NotificationsReadSerializer(data=request.data)
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
        data = serializer.validated_data
        qs = Notification.objects.filter(recipient=request.user)
        if data.get('all'):
            qs.update(is_read=True)
        elif data.get('ids'):
            qs.filter(id__in=data['ids']).update(is_read=True)
        return Response(None, status=status.HTTP_204_NO_CONTENT)


class DeviceRegisterView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        serializer = DeviceSerializer(data=request.data)
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
        data = serializer.validated_data
        token = data['fcm_token']
        # A physical device belongs to whoever last signed in on it — drop any
        # other account's claim on this token so pushes don't reach a device
        # after that user has logged out and someone else uses it.
        Device.objects.filter(fcm_token=token).exclude(user=request.user).delete()
        Device.objects.update_or_create(
            user=request.user,
            fcm_token=token,
            defaults={'platform': data.get('platform', 'web')},
        )
        return Response(None, status=status.HTTP_204_NO_CONTENT)

    def delete(self, request):
        # Called on logout to stop this device receiving the user's pushes.
        # With a token, unregister just this device; without, all of theirs.
        qs = Device.objects.filter(user=request.user)
        token = request.query_params.get('token')
        if token:
            qs = qs.filter(fcm_token=token)
        qs.delete()
        return Response(None, status=status.HTTP_204_NO_CONTENT)
