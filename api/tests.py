from datetime import date

from rest_framework.test import APITestCase
from rest_framework import status

from accounts.models import AdminActionLog, CustomUser, Driver, Parent
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


def make_super_admin(phone="0700000010"):
    return CustomUser.objects.create(
        phone=phone, role=CustomUser.Role.ADMIN, is_staff=True, is_superuser=True,
    )


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


class AdminStaffTest(APITestCase):
    """Only Super Admins (is_superuser) may manage console accounts. Regular
    admins can view the staff list but not add or deactivate other admins."""

    def setUp(self):
        self.super_admin = make_super_admin()
        self.admin = make_admin()

    def test_list_reports_can_manage_true_for_super_admin(self):
        self.client.force_authenticate(user=self.super_admin)
        resp = self.client.get("/api/admin/staff")
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertTrue(resp.data["can_manage"])
        # The super admin's own row is flagged.
        me = next(r for r in resp.data["results"] if r["id"] == self.super_admin.id)
        self.assertTrue(me["is_super_admin"])
        self.assertTrue(me["is_you"])

    def test_list_reports_can_manage_false_for_regular_admin(self):
        self.client.force_authenticate(user=self.admin)
        resp = self.client.get("/api/admin/staff")
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertFalse(resp.data["can_manage"])

    def test_super_admin_can_create_admin_and_it_is_logged(self):
        self.client.force_authenticate(user=self.super_admin)
        resp = self.client.post(
            "/api/admin/staff",
            {"full_name": "New Admin", "phone": "0700000123", "password": "secret1"},
            format="json",
        )
        self.assertEqual(resp.status_code, status.HTTP_201_CREATED)
        created = CustomUser.objects.get(phone="0700000123")
        self.assertEqual(created.role, CustomUser.Role.ADMIN)
        self.assertTrue(created.is_staff)
        self.assertFalse(created.is_superuser)  # new admins are not Super Admins
        self.assertFalse(resp.data["is_super_admin"])
        self.assertTrue(AdminActionLog.objects.filter(action="staff.create", target_id=str(created.id)).exists())

    def test_regular_admin_cannot_create_admin(self):
        self.client.force_authenticate(user=self.admin)
        resp = self.client.post(
            "/api/admin/staff",
            {"full_name": "Nope", "phone": "0700000124", "password": "secret1"},
            format="json",
        )
        self.assertEqual(resp.status_code, status.HTTP_403_FORBIDDEN)
        self.assertFalse(CustomUser.objects.filter(phone="0700000124").exists())

    def test_super_admin_can_toggle_another_admin_and_it_is_logged(self):
        self.client.force_authenticate(user=self.super_admin)
        resp = self.client.post(f"/api/admin/staff/{self.admin.id}/toggle")
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.admin.refresh_from_db()
        self.assertFalse(self.admin.is_active)
        self.assertTrue(AdminActionLog.objects.filter(action="staff.deactivate", target_id=str(self.admin.id)).exists())

    def test_super_admin_cannot_deactivate_self(self):
        self.client.force_authenticate(user=self.super_admin)
        resp = self.client.post(f"/api/admin/staff/{self.super_admin.id}/toggle")
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)
        self.super_admin.refresh_from_db()
        self.assertTrue(self.super_admin.is_active)

    def test_regular_admin_cannot_toggle(self):
        self.client.force_authenticate(user=self.admin)
        resp = self.client.post(f"/api/admin/staff/{self.super_admin.id}/toggle")
        self.assertEqual(resp.status_code, status.HTTP_403_FORBIDDEN)


class AdminAuditLogTest(APITestCase):
    """Mutating admin actions are recorded and readable via /admin/audit."""

    def setUp(self):
        self.admin = make_admin()
        self.driver = make_driver()
        self.client.force_authenticate(user=self.admin)

    def test_mutating_action_is_recorded_and_listed(self):
        self.driver.is_verified = False
        self.driver.save()

        resp = self.client.post(f"/api/admin/drivers/{self.driver.id}/approve")
        self.assertEqual(resp.status_code, status.HTTP_200_OK)

        entry = AdminActionLog.objects.filter(action="driver.approve").first()
        self.assertIsNotNone(entry)
        self.assertEqual(entry.actor, self.admin)

        listing = self.client.get("/api/admin/audit")
        self.assertEqual(listing.status_code, status.HTTP_200_OK)
        self.assertGreaterEqual(listing.data["count"], 1)
        self.assertTrue(any(r["action"] == "driver.approve" for r in listing.data["results"]))

    def test_audit_search_filters_results(self):
        self.client.post(f"/api/admin/drivers/{self.driver.id}/approve")
        resp = self.client.get("/api/admin/audit", {"q": "no-such-actor-xyz"})
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertEqual(resp.data["count"], 0)

    def test_audit_requires_admin(self):
        self.client.force_authenticate(user=self.driver.user)
        resp = self.client.get("/api/admin/audit")
        self.assertEqual(resp.status_code, status.HTTP_403_FORBIDDEN)
