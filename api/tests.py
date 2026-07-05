from datetime import date

from rest_framework.test import APITestCase
from rest_framework import status

from accounts.models import CustomUser, Driver, Parent
from children.models import School, Child
from trips.models import Assignment, Trip, Stop
from incidents.models import Incident
from main.gis_fallback import GeoPoint


def make_driver(phone="0700000001"):
    user = CustomUser.objects.create(phone=phone, role=CustomUser.Role.DRIVER)
    user.set_password("password")
    user.save()
    return Driver.objects.create(user=user, plate=f"UAB-{phone[-3:]}", is_verified=True)


def make_parent(phone="0700000002"):
    user = CustomUser.objects.create(phone=phone, role=CustomUser.Role.PARENT)
    user.set_password("password")
    user.save()
    return Parent.objects.create(user=user)


def make_admin(phone="0700000009"):
    return CustomUser.objects.create(phone=phone, role=CustomUser.Role.ADMIN, is_staff=True)


def make_child(parent, school):
    return Child.objects.create(
        parent=parent, school=school, full_name="Test Child",
        pickup_address="Somewhere", pickup_point=GeoPoint(32.58, 0.31),
    )


def make_trip_with_stop(driver, child, direction=Trip.Direction.TO_SCHOOL, status_=Trip.Status.IN_PROGRESS):
    trip = Trip.objects.create(
        driver=driver, service_date=date.today(), direction=direction, status=status_,
    )
    stop = Stop.objects.create(trip=trip, child=child, sequence=1, status=Stop.Status.NEXT)
    return trip, stop


class NoShowEscalationTest(APITestCase):
    """A no-show must not just notify the parent — it has to surface to
    admin as an open Incident so ops can act while the child is still
    stranded, not discover it later by chance."""

    def setUp(self):
        self.driver = make_driver()
        self.parent = make_parent()
        self.school = School.objects.create(name="Test School", location=GeoPoint(32.6, 0.3))
        self.child = make_child(self.parent, self.school)
        Assignment.objects.create(driver=self.driver, parent=self.parent, is_active=True)
        self.trip, self.stop = make_trip_with_stop(self.driver, self.child)
        make_admin()
        self.client.force_authenticate(user=self.driver.user)

    def test_no_show_creates_open_incident_for_admin(self):
        resp = self.client.post(
            f"/api/stops/{self.stop.id}/no-show", {"reason": "No answer at gate"}, format="json",
        )
        self.assertEqual(resp.status_code, status.HTTP_200_OK)

        incident = Incident.objects.filter(incident_type=Incident.NO_SHOW).first()
        self.assertIsNotNone(incident)
        self.assertEqual(incident.status, Incident.OPEN)
        self.assertEqual(incident.child_id, self.child.id)
        self.assertEqual(incident.trip_id, self.trip.id)
        self.assertEqual(incident.triggered_by, self.driver.user)
        self.assertTrue(incident.timeline.filter(event_text__icontains="No answer at gate").exists())

    def test_only_a_driver_can_mark_no_show(self):
        self.client.force_authenticate(user=self.parent.user)
        resp = self.client.post(
            f"/api/stops/{self.stop.id}/no-show", {"reason": "x"}, format="json",
        )
        self.assertEqual(resp.status_code, status.HTTP_403_FORBIDDEN)
        self.assertFalse(Incident.objects.filter(incident_type=Incident.NO_SHOW).exists())


class IncidentReportTest(APITestCase):
    """The Trust & Safety self-report path: drivers/parents can flag a
    non-panic problem, scoped so nobody can report against someone else's
    child or trip, and can't smuggle in a panic_alert."""

    def setUp(self):
        self.driver = make_driver()
        self.other_driver = make_driver(phone="0700000003")
        self.parent = make_parent()
        self.other_parent = make_parent(phone="0700000004")
        self.school = School.objects.create(name="Test School", location=GeoPoint(32.6, 0.3))
        self.child = make_child(self.parent, self.school)
        self.other_child = make_child(self.other_parent, self.school)
        Assignment.objects.create(driver=self.driver, parent=self.parent, is_active=True)
        self.trip, _ = make_trip_with_stop(self.driver, self.child)

    def test_parent_can_report_for_own_child(self):
        self.client.force_authenticate(user=self.parent.user)
        resp = self.client.post(
            "/api/incidents",
            {"incident_type": "SICK_CHILD", "description": "Feeling unwell today", "child_id": str(self.child.id)},
            format="json",
        )
        self.assertEqual(resp.status_code, status.HTTP_201_CREATED)
        incident = Incident.objects.get(incident_id=resp.data["id"])
        self.assertEqual(incident.incident_type, Incident.SICK_CHILD)
        self.assertEqual(incident.child_id, self.child.id)
        self.assertEqual(incident.triggered_by, self.parent.user)

    def test_parent_cannot_report_for_someone_elses_child(self):
        self.client.force_authenticate(user=self.parent.user)
        resp = self.client.post(
            "/api/incidents",
            {"description": "x", "child_id": str(self.other_child.id)},
            format="json",
        )
        self.assertEqual(resp.status_code, status.HTTP_404_NOT_FOUND)

    def test_driver_can_report_route_issue_for_own_trip(self):
        self.client.force_authenticate(user=self.driver.user)
        resp = self.client.post(
            "/api/incidents",
            {"incident_type": "ROUTE_DEVIATION", "description": "Road closed", "trip_id": str(self.trip.id)},
            format="json",
        )
        self.assertEqual(resp.status_code, status.HTTP_201_CREATED)

    def test_driver_cannot_report_against_another_drivers_trip(self):
        other_trip, _ = make_trip_with_stop(self.other_driver, self.other_child)
        self.client.force_authenticate(user=self.driver.user)
        resp = self.client.post(
            "/api/incidents",
            {"description": "x", "trip_id": str(other_trip.id)},
            format="json",
        )
        self.assertEqual(resp.status_code, status.HTTP_404_NOT_FOUND)

    def test_defaults_to_other_type_and_requires_description(self):
        self.client.force_authenticate(user=self.parent.user)
        resp = self.client.post("/api/incidents", {"description": "General issue"}, format="json")
        self.assertEqual(resp.status_code, status.HTTP_201_CREATED)
        incident = Incident.objects.get(incident_id=resp.data["id"])
        self.assertEqual(incident.incident_type, Incident.OTHER)

        resp = self.client.post("/api/incidents", {}, format="json")
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)

    def test_panic_alert_is_rejected_as_an_invalid_choice(self):
        self.client.force_authenticate(user=self.parent.user)
        resp = self.client.post(
            "/api/incidents",
            {"incident_type": "PANIC_ALERT", "description": "x"},
            format="json",
        )
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)

    def test_requires_authentication(self):
        resp = self.client.post("/api/incidents", {"description": "x"}, format="json")
        self.assertEqual(resp.status_code, status.HTTP_401_UNAUTHORIZED)
