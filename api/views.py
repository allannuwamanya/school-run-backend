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

from accounts.models import CustomUser, Parent, Driver, Notification, Device
from children.models import Child, School, Schedule
from trips.models import Trip, Stop, Assignment

from main.firebase_push import send_push

from .serializers import (
    RegisterSerializer,
    LoginSerializer,
    MeSerializer,
    MePatchSerializer,
    SchoolSerializer,
    ChildListSerializer,
    ChildCreateSerializer,
    SchedulePutSerializer,
    DashboardSerializer,
    ParentDriverSerializer,
    ManifestSerializer,
    ManifestTripSerializer,
    StopEventSerializer,
    StopNoShowSerializer,
    StopEventResultSerializer,
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
            },
        })


class MeView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        serializer = MeSerializer(request.user)
        return ok(serializer.data)

    def patch(self, request):
        serializer = MePatchSerializer(data=request.data)
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
        data = serializer.validated_data
        if 'full_name' in data:
            request.user.full_name = data['full_name']
        if 'preferences' in data:
            prefs = data['preferences']
            if 'push' in prefs:
                request.user.push_notifications_enabled = prefs['push']
            if 'location_sharing' in prefs:
                request.user.location_sharing_enabled = prefs['location_sharing']
            if 'dark_mode' in prefs:
                request.user.dark_mode = prefs['dark_mode']
        request.user.save()
        return ok(MeSerializer(request.user).data)


class SchoolListView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        q = request.query_params.get('q', '')
        schools = School.objects.all()
        if q:
            schools = schools.filter(name__icontains=q)
        serializer = SchoolSerializer(schools, many=True)
        return ok(serializer.data)


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
        children = Child.objects.filter(parent=parent, is_active=True)
        serializer = DashboardSerializer({'children': list(children)})
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
        stop.status = Stop.Status.NO_SHOW
        stop.save()
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
        else:
            stop.status = Stop.Status.DROPPED
            stop.dropped_at = timezone.now()
            stop.dropped_point = point
        if trip.status == Trip.Status.SCHEDULED:
            trip.status = Trip.Status.IN_PROGRESS
            trip.save()
        stop.save()

        notif = Notification.objects.create(
            recipient=stop.child.parent.user,
            kind='PICKUP' if kind == 'pickup' else 'DROPOFF',
            title=f'{stop.child.full_name} {"picked up" if kind == "pickup" else "dropped off"}',
            body=f'{stop.child.full_name} was {"collected" if kind == "pickup" else "dropped"} by {request.user.full_name}.',
        )
        try:
            send_push(
                notif.recipient,
                notif.title,
                notif.body,
                {'kind': notif.kind, 'stop_id': str(stop.id)},
            )
        except Exception:
            pass

    next_stop = Stop.objects.filter(trip=trip, sequence__gt=stop.sequence, status=Stop.Status.UPCOMING).order_by('sequence').first()
    if next_stop:
        next_stop.status = Stop.Status.NEXT
        next_stop.save()

    result_data = {
        'stop': stop,
        'gps_verified': gps_verified if kind != 'no-show' else None,
        'distance_m': distance_m if kind != 'no-show' else None,
        'next_stop': next_stop,
    }
    serializer_result = StopEventResultSerializer(result_data)
    return ok(serializer_result.data)


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


class HistoryView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        try:
            parent = Parent.objects.get(user=request.user)
        except Parent.DoesNotExist:
            return err('Only parents can view history.', 403)
        t = request.query_params.get('type', 'all')
        trips = Trip.objects.filter(
            stops__child__parent=parent,
            status=Trip.Status.COMPLETED,
        ).distinct().order_by('-service_date')[:50]
        history = []
        for trip in trips:
            stops = trip.stops.filter(child__parent=parent)
            for stop in stops:
                history.append({
                    'id': stop.id,
                    'type': 'RIDE',
                    'at': stop.picked_at or stop.dropped_at or trip.service_date,
                    'title': f'{stop.child.full_name} — {"School" if trip.direction == "TO_SCHOOL" else "Home"}',
                    'subtitle': f'{trip.driver.user.full_name} · {trip.driver.plate} · {stop.child.school.name}',
                    'amount': None,
                    'label': 'Completed',
                })
        if t == 'rides':
            history = [h for h in history if h['type'] == 'RIDE']
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
        Device.objects.update_or_create(
            user=request.user,
            fcm_token=data['fcm_token'],
            defaults={'platform': data.get('platform', 'web')},
        )
        return Response(None, status=status.HTTP_204_NO_CONTENT)
