from datetime import date, time
from django.test import TestCase
from accounts.models import CustomUser, Driver, Parent
from children.models import School, Child, Schedule
from trips.models import Assignment, Trip, Stop
from trips.tasks import _haversine_m, _nearest_neighbour, generate_daily_manifests
from main.gis_fallback import GeoPoint

class HaversineTest(TestCase):
    def test_haversine_distance(self):
        # Coordinates for two points in Kampala
        p1 = (32.5825, 0.3476) # (lng, lat)
        p2 = (32.5938, 0.3551)
        dist = _haversine_m(p1, p2)
        # Should be roughly 1500 - 1600 meters
        self.assertTrue(1400 < dist < 1700)


class NearestNeighbourTest(TestCase):
    def test_ordering(self):
        # We need a parent and school to create child objects
        user = CustomUser.objects.create(phone="0711111111", role=CustomUser.Role.PARENT)
        parent = Parent.objects.create(user=user)
        school = School.objects.create(name="Greenhill Academy", location=GeoPoint(32.6, 0.3))

        # Create three children with pickup points
        c1 = Child.objects.create(
            parent=parent, school=school, full_name="Child One",
            pickup_address="A", pickup_point=GeoPoint(32.58, 0.31)
        )
        c2 = Child.objects.create(
            parent=parent, school=school, full_name="Child Two",
            pickup_address="B", pickup_point=GeoPoint(32.58, 0.32) # Closer to c1
        )
        c3 = Child.objects.create(
            parent=parent, school=school, full_name="Child Three",
            pickup_address="C", pickup_point=GeoPoint(32.59, 0.33) # Farther
        )

        ordered = _nearest_neighbour([c3, c2, c1])
        # The deterministic anchor will pick the southern-then-western-most:
        # c1 has y=0.31, c2 has y=0.32, c3 has y=0.33. So c1 is southernmost (y=0.31).
        # Nearest to c1 is c2 (y=0.32 vs c3 y=0.33). So ordering should be c1 -> c2 -> c3.
        self.assertEqual(ordered[0], c1)
        self.assertEqual(ordered[1], c2)
        self.assertEqual(ordered[2], c3)


class ManifestGenerationTest(TestCase):
    def test_generate_daily_manifests(self):
        # Set up a parent, driver, assignment, school, child, schedule
        driver_user = CustomUser.objects.create(phone="0722222222", role=CustomUser.Role.DRIVER)
        driver = Driver.objects.create(user=driver_user, plate="UAB 123X", is_verified=True)

        parent_user = CustomUser.objects.create(phone="0733333333", role=CustomUser.Role.PARENT)
        parent = Parent.objects.create(user=parent_user)

        Assignment.objects.create(driver=driver, parent=parent, is_active=True)

        school = School.objects.create(name="Greenhill Academy", location=GeoPoint(32.6, 0.3))

        # Child with schedule on Mon (isoweekday = 1)
        child = Child.objects.create(
            parent=parent, school=school, full_name="Kid A",
            pickup_address="Home A", pickup_point=GeoPoint(32.58, 0.31)
        )
        Schedule.objects.create(
            child=child,
            morning_time=time(7, 0),
            afternoon_time=time(16, 30),
            days=[1] # Monday
        )

        # Run manifest generator for a Monday (e.g. 2026-07-06 is a Monday)
        res = generate_daily_manifests("2026-07-06")
        self.assertEqual(res["trips_created"], 2) # TO_SCHOOL and TO_HOME

        # Verify Trips and Stops created
        trips = Trip.objects.filter(driver=driver, service_date="2026-07-06")
        self.assertEqual(trips.count(), 2)

        to_school_trip = trips.get(direction=Trip.Direction.TO_SCHOOL)
        self.assertEqual(to_school_trip.status, Trip.Status.SCHEDULED)
        self.assertEqual(to_school_trip.stops.count(), 1)

        stop = to_school_trip.stops.first()
        self.assertEqual(stop.child, child)
        self.assertEqual(stop.sequence, 1)
        self.assertEqual(stop.status, Stop.Status.UPCOMING)
        self.assertEqual(stop.eta, time(7, 0))
