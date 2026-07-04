from datetime import date

from rest_framework import serializers
from django.contrib.auth import authenticate
from accounts.models import CustomUser, Parent, Driver, VerificationDocument, Notification
from children.models import Child, School, Schedule
from trips.models import Trip, Stop, Assignment
from main.gis_fallback import GeoPoint


class LatLngField(serializers.Field):
    def to_representation(self, value):
        if value is None:
            return None
        return {'lat': float(value.y), 'lng': float(value.x)}

    def to_internal_value(self, data):
        return GeoPoint(float(data['lng']), float(data['lat']))


class AuthUserSerializer(serializers.ModelSerializer):
    class Meta:
        model = CustomUser
        fields = ['id', 'role', 'full_name', 'phone']


class RegisterSerializer(serializers.ModelSerializer):
    password = serializers.CharField(write_only=True, min_length=6)
    emergency_contact = serializers.CharField(write_only=True, required=False, allow_blank=True)

    class Meta:
        model = CustomUser
        fields = ['phone', 'password', 'full_name', 'emergency_contact']

    def create(self, validated_data):
        emergency_contact = validated_data.pop('emergency_contact', '')
        user = CustomUser.objects.create_user(
            phone=validated_data['phone'],
            password=validated_data['password'],
            full_name=validated_data.get('full_name', ''),
            role=CustomUser.Role.PARENT,
        )
        Parent.objects.create(user=user, emergency_contact=emergency_contact)
        return user


class LoginSerializer(serializers.Serializer):
    phone = serializers.CharField()
    password = serializers.CharField(write_only=True)

    def validate(self, attrs):
        user = authenticate(phone=attrs['phone'], password=attrs['password'])
        if not user:
            raise serializers.ValidationError('Invalid phone or password.')
        if not user.is_active:
            raise serializers.ValidationError('Account disabled.')
        attrs['user'] = user
        return attrs


class GoogleLoginSerializer(serializers.Serializer):
    credential = serializers.CharField()

    def validate(self, attrs):
        from google.auth.transport import requests as google_requests
        from google.oauth2 import id_token as google_id_token
        from django.conf import settings

        try:
            idinfo = google_id_token.verify_oauth2_token(
                attrs['credential'], google_requests.Request(), settings.GOOGLE_CLIENT_ID,
            )
        except ValueError:
            raise serializers.ValidationError('Invalid Google credential.')

        email = idinfo.get('email')
        if not email or not idinfo.get('email_verified'):
            raise serializers.ValidationError('Google account has no verified email.')

        user = CustomUser.objects.filter(email__iexact=email).first()
        if not user:
            # phone=None (not the CharField default of '') so a unique
            # constraint allows any number of Google-only accounts.
            user = CustomUser(
                phone=None,
                email=email,
                full_name=idinfo.get('name', ''),
                role=CustomUser.Role.PARENT,
            )
            user.set_unusable_password()
            user.save()
            Parent.objects.create(user=user)

        if not user.is_active:
            raise serializers.ValidationError('Account disabled.')
        attrs['user'] = user
        return attrs


class MeSerializer(serializers.Serializer):
    user = serializers.SerializerMethodField()
    is_verified = serializers.SerializerMethodField()
    preferences = serializers.SerializerMethodField()

    def get_user(self, obj):
        return AuthUserSerializer(obj).data

    def get_is_verified(self, obj):
        try:
            return obj.parent.is_verified
        except Parent.DoesNotExist:
            return False

    def get_preferences(self, obj):
        return {
            'push': obj.push_notifications_enabled,
            'location_sharing': obj.location_sharing_enabled,
            'dark_mode': obj.dark_mode,
        }


class MePatchSerializer(serializers.Serializer):
    full_name = serializers.CharField(required=False)
    preferences = serializers.DictField(required=False, child=serializers.BooleanField())


class SchoolSerializer(serializers.ModelSerializer):
    point = LatLngField(source='location')

    class Meta:
        model = School
        fields = ['id', 'name', 'address', 'point']


class SchoolNestedSerializer(serializers.Serializer):
    id = serializers.UUIDField()
    name = serializers.CharField()


class ScheduleSerializer(serializers.Serializer):
    morning_time = serializers.TimeField(format='%H:%M')
    afternoon_time = serializers.TimeField(format='%H:%M')
    days = serializers.ListField(child=serializers.IntegerField())


class ChildListSerializer(serializers.ModelSerializer):
    school = SchoolNestedSerializer()
    pickup_point = LatLngField()
    schedule = serializers.SerializerMethodField()
    photo = serializers.SerializerMethodField()

    class Meta:
        model = Child
        fields = [
            'id', 'full_name', 'date_of_birth', 'gender', 'blood_type',
            'class_name', 'allergies', 'photo', 'school', 'pickup_address',
            'pickup_point', 'is_active', 'schedule',
        ]

    def get_schedule(self, obj):
        try:
            s = obj.schedule
            return ScheduleSerializer(s).data
        except Schedule.DoesNotExist:
            return None

    def get_photo(self, obj):
        if obj.photo:
            return obj.photo.url
        return None


class ChildCreateSerializer(serializers.ModelSerializer):
    school_id = serializers.UUIDField()
    pickup_point = LatLngField()
    date_of_birth = serializers.DateField(required=False, allow_null=True)
    gender = serializers.ChoiceField(choices=Child.Gender.choices, required=False, allow_blank=True)
    blood_type = serializers.CharField(required=False, allow_blank=True)
    class_name = serializers.CharField(required=False, allow_blank=True)
    allergies = serializers.CharField(required=False, allow_blank=True)

    class Meta:
        model = Child
        fields = [
            'full_name', 'date_of_birth', 'gender', 'blood_type', 'class_name',
            'allergies', 'school_id', 'pickup_address', 'pickup_point',
        ]

    def create(self, validated_data):
        school_id = validated_data.pop('school_id')
        validated_data['school'] = School.objects.get(id=school_id)
        parent_user = self.context['request'].user
        validated_data['parent'] = Parent.objects.get(user=parent_user)
        return super().create(validated_data)


class SchedulePutSerializer(serializers.Serializer):
    morning_time = serializers.TimeField()
    afternoon_time = serializers.TimeField()
    days = serializers.ListField(child=serializers.IntegerField())


class DashboardChildSerializer(serializers.Serializer):
    child = serializers.SerializerMethodField()
    today = serializers.SerializerMethodField()
    driver = serializers.SerializerMethodField()

    def get_child(self, obj):
        return {
            'id': str(obj.id),
            'full_name': obj.full_name,
            'photo': obj.photo.url if obj.photo else None,
            'school_name': obj.school.name,
        }

    def get_today(self, obj):
        today_stop = Stop.objects.filter(
            child=obj,
            trip__service_date=today_date(),
        ).select_related('trip').first()
        if not today_stop:
            return None
        trip = today_stop.trip
        all_stops = Stop.objects.filter(trip=trip).order_by('sequence')
        total = all_stops.count()
        last_event = None
        if today_stop.dropped_at:
            last_event = {
                'type': today_stop.status,
                'at': today_stop.dropped_at.isoformat(),
                'point': (
                    {'lat': float(today_stop.dropped_point.y), 'lng': float(today_stop.dropped_point.x)}
                    if today_stop.dropped_point else None
                ),
            }
        elif today_stop.picked_at:
            last_event = {
                'type': today_stop.status,
                'at': today_stop.picked_at.isoformat(),
                'point': (
                    {'lat': float(today_stop.picked_point.y), 'lng': float(today_stop.picked_point.x)}
                    if today_stop.picked_point else None
                ),
            }
        return {
            'direction': trip.direction,
            'trip_status': trip.status,
            'stop_status': today_stop.status,
            'eta': today_stop.eta.strftime('%H:%M') if today_stop.eta else None,
            'position': f'{today_stop.sequence} of {total}',
            'last_event': last_event,
        }

    def get_driver(self, obj):
        try:
            assignment = Assignment.objects.get(parent=obj.parent, is_active=True)
            driver = assignment.driver
            return {
                'id': str(driver.id),
                'full_name': driver.user.full_name,
                'plate': driver.plate,
                'phone': driver.user.phone,
                'photo': None,
                'rating': float(driver.rating),
            }
        except Assignment.DoesNotExist:
            return None


class DashboardSerializer(serializers.Serializer):
    children = serializers.ListField(child=DashboardChildSerializer())


class ParentDriverSerializer(serializers.Serializer):
    driver = serializers.SerializerMethodField()
    documents = serializers.SerializerMethodField()
    all_verified = serializers.SerializerMethodField()

    def get_driver(self, obj):
        return {
            'id': str(obj.id),
            'full_name': obj.user.full_name,
            'since': obj.driver_since.isoformat() if obj.driver_since else '2024-01',
            'trips': obj.trips.count() if hasattr(obj, 'trips') else 0,
            'rating': float(obj.rating),
            'vehicle': f'{obj.vehicle_make} {obj.vehicle_model}'.strip(),
            'plate': obj.plate,
            'color': obj.color,
            'phone': obj.user.phone,
        }

    def get_documents(self, obj):
        docs = obj.documents.all()
        return [{'doc_type': d.doc_type, 'status': d.status} for d in docs]

    def get_all_verified(self, obj):
        docs = obj.documents.all()
        if not docs:
            return False
        return all(d.status in ('VERIFIED', 'CLEAR') for d in docs)


class ManifestStopSerializer(serializers.Serializer):
    id = serializers.SerializerMethodField()
    sequence = serializers.IntegerField()
    status = serializers.CharField()
    eta = serializers.SerializerMethodField()
    address = serializers.SerializerMethodField()
    point = serializers.SerializerMethodField()
    child = serializers.SerializerMethodField()
    picked_at = serializers.SerializerMethodField()
    dropped_at = serializers.SerializerMethodField()

    def get_id(self, obj):
        return str(obj.id)

    def get_eta(self, obj):
        return obj.eta.strftime('%H:%M') if obj.eta else None

    def get_address(self, obj):
        return obj.child.pickup_address

    def get_point(self, obj):
        p = obj.child.pickup_point
        if p:
            return {'lat': float(p.y), 'lng': float(p.x)}
        return None

    def get_child(self, obj):
        return {
            'id': str(obj.child.id),
            'full_name': obj.child.full_name,
            'allergies': obj.child.allergies,
            'photo': obj.child.photo.url if obj.child.photo else None,
        }

    def get_picked_at(self, obj):
        return obj.picked_at.isoformat() if obj.picked_at else None

    def get_dropped_at(self, obj):
        return obj.dropped_at.isoformat() if obj.dropped_at else None


class ManifestTripSerializer(serializers.Serializer):
    id = serializers.SerializerMethodField()
    direction = serializers.CharField()
    status = serializers.CharField()
    summary = serializers.SerializerMethodField()
    stops = serializers.SerializerMethodField()

    def get_id(self, obj):
        return str(obj.id)

    def get_summary(self, obj):
        stops = obj.stops.all()
        pending = [s for s in stops if s.status not in ('PICKED_UP', 'DROPPED')]
        return {
            'children': stops.count(),
            'stops': len(pending),
            'distance_km': 11,
            'est_minutes': 45,
        }

    def get_stops(self, obj):
        return ManifestStopSerializer(obj.stops.order_by('sequence'), many=True).data


class ManifestSerializer(serializers.Serializer):
    trips = serializers.ListField(child=ManifestTripSerializer())


class StopEventSerializer(serializers.Serializer):
    lat = serializers.FloatField(required=False)
    lng = serializers.FloatField(required=False)


class StopNoShowSerializer(serializers.Serializer):
    reason = serializers.CharField()


class StopEventResultSerializer(serializers.Serializer):
    id = serializers.SerializerMethodField()
    status = serializers.SerializerMethodField()
    picked_at = serializers.SerializerMethodField()
    dropped_at = serializers.SerializerMethodField()
    picked_point = serializers.SerializerMethodField()
    dropped_point = serializers.SerializerMethodField()
    gps_verified = serializers.SerializerMethodField()
    distance_m = serializers.SerializerMethodField()
    next_stop_id = serializers.SerializerMethodField()

    def get_id(self, obj):
        return str(obj['stop'].id)

    def get_status(self, obj):
        return obj['stop'].status

    def get_picked_at(self, obj):
        return obj['stop'].picked_at.isoformat() if obj['stop'].picked_at else None

    def get_dropped_at(self, obj):
        return obj['stop'].dropped_at.isoformat() if obj['stop'].dropped_at else None

    def get_picked_point(self, obj):
        p = obj['stop'].picked_point
        if p:
            return {'lat': float(p.y), 'lng': float(p.x)}
        return None

    def get_dropped_point(self, obj):
        p = obj['stop'].dropped_point
        if p:
            return {'lat': float(p.y), 'lng': float(p.x)}
        return None

    def get_gps_verified(self, obj):
        return obj.get('gps_verified')

    def get_distance_m(self, obj):
        return obj.get('distance_m')

    def get_next_stop_id(self, obj):
        n = obj.get('next_stop')
        return str(n.id) if n else None


class HistoryRowSerializer(serializers.Serializer):
    id = serializers.SerializerMethodField()
    type = serializers.CharField()
    at = serializers.DateTimeField()
    title = serializers.CharField()
    subtitle = serializers.CharField()
    amount = serializers.SerializerMethodField()
    label = serializers.CharField()

    def get_id(self, obj):
        return str(obj.id)

    def get_amount(self, obj):
        return None


class NotificationSerializer(serializers.ModelSerializer):
    kind = serializers.CharField()
    is_read = serializers.BooleanField()
    created_at = serializers.DateTimeField()

    class Meta:
        model = Notification
        fields = ['id', 'kind', 'title', 'body', 'is_read', 'created_at']


class NotificationsReadSerializer(serializers.Serializer):
    ids = serializers.ListField(child=serializers.CharField(), required=False)
    all = serializers.BooleanField(required=False)


class DeviceSerializer(serializers.Serializer):
    fcm_token = serializers.CharField()
    platform = serializers.CharField()


def today_date():
    return date.today()
