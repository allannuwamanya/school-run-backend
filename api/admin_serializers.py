"""
Plain-function serializers for the internal Admin console (/api/admin/*).

These build the exact JSON shapes the frontend's src/api/types.ts Admin*
interfaces expect (originally designed against a mock backend). Several
metrics (trend percentages, "on-time %") have no historical snapshot table
to compare against yet, so they're computed as real aggregates over current
data rather than fabricated — trend fields report 0 until that history
exists.
"""
from django.utils import timezone

from accounts.models import CustomUser, VerificationDocument
from incidents.models import Incident
from payments.models import Subscription, Transaction
from trips.models import Assignment, Stop

REQUIRED_DOC_TYPES = [
    VerificationDocument.DocType.LICENSE,
    VerificationDocument.DocType.INSPECTION,
    VerificationDocument.DocType.BACKGROUND,
]
DOC_LABEL = {
    VerificationDocument.DocType.LICENSE: "License",
    VerificationDocument.DocType.INSPECTION: "Inspection",
    VerificationDocument.DocType.BACKGROUND: "Background Check",
}


def _zone_name(obj):
    return obj.zone.name if obj.zone else "Unassigned"


def _doc_map(driver):
    return {d.doc_type: d for d in driver.documents.all()}


def _driver_documents(driver):
    docs = _doc_map(driver)
    out = []
    for doc_type in REQUIRED_DOC_TYPES:
        doc = docs.get(doc_type)
        if doc is None:
            ok = False
        elif doc.status in (VerificationDocument.Status.VERIFIED, VerificationDocument.Status.CLEAR):
            ok = True
        elif doc.status == VerificationDocument.Status.PENDING:
            ok = "pending"
        else:
            ok = False
        out.append({"label": DOC_LABEL[doc_type], "ok": ok})
    return out


def _bgc_status(driver):
    doc = _doc_map(driver).get(VerificationDocument.DocType.BACKGROUND)
    if doc is None:
        return "NOT_STARTED"
    if doc.status in (VerificationDocument.Status.VERIFIED, VerificationDocument.Status.CLEAR):
        return "CLEARED"
    if doc.status == VerificationDocument.Status.PENDING:
        return "PENDING"
    return "PENDING"  # REJECTED — treated as still needing action


def _docs_missing(driver):
    docs = _doc_map(driver)
    return sum(1 for t in REQUIRED_DOC_TYPES if t not in docs)


def serialize_driver_list_item(driver):
    return {
        "id": str(driver.id),
        "full_name": driver.user.full_name or driver.user.phone,
        "phone": driver.user.phone,
        "zone": _zone_name(driver),
        "vehicle": f"{driver.vehicle_make} {driver.vehicle_model}".strip(),
        "documents": _driver_documents(driver),
        "bgc_status": _bgc_status(driver),
        "days_pending": 0 if driver.is_verified else (timezone.now() - driver.created_at).days,
        "is_ready": driver.is_verified,
        "docs_missing": _docs_missing(driver),
    }


def serialize_driver_detail(driver):
    docs = _doc_map(driver)
    checklist = []
    for doc_type in REQUIRED_DOC_TYPES:
        doc = docs.get(doc_type)
        if doc is None:
            status = "MISSING"
        elif doc.status in (VerificationDocument.Status.VERIFIED, VerificationDocument.Status.CLEAR):
            status = "VERIFIED"
        elif doc.status == VerificationDocument.Status.PENDING:
            status = "PENDING"
        else:
            status = "REVIEW"
        checklist.append({"label": DOC_LABEL[doc_type], "status": status})

    experience_years = 0
    if driver.driver_since:
        experience_years = max(0, (timezone.now().date() - driver.driver_since).days // 365)

    return {
        **serialize_driver_list_item(driver),
        "experience_years": experience_years,
        "plate": driver.plate,
        "applied": driver.created_at.date().isoformat(),
        "checklist": checklist,
    }


def _plan_tier(subscription):
    if not subscription or not subscription.plan:
        return "STANDARD"
    name = subscription.plan.name.lower()
    if "family" in name:
        return "FAMILY_PLUS"
    if "premium" in name:
        return "PREMIUM"
    return "STANDARD"


def _active_subscription(parent):
    return parent.subscriptions.order_by("-started_at").first()


def _parent_account_status(parent, sub):
    if not parent.user.is_active:
        return "SUSPENDED"
    if sub and sub.status == Subscription.OVERDUE:
        return "OVERDUE"
    return "ACTIVE"


def serialize_parent_row(parent):
    sub = _active_subscription(parent)
    assignment = Assignment.objects.filter(parent=parent, is_active=True).select_related("driver__user").first()
    return {
        "id": str(parent.id),
        "full_name": parent.user.full_name or parent.user.phone,
        "phone": parent.user.phone,
        "children_count": parent.children.filter(is_active=True).count(),
        "zone": _zone_name(parent),
        "plan": _plan_tier(sub),
        "driver_name": assignment.driver.user.full_name if assignment else None,
        "last_active": parent.user.last_login.isoformat() if parent.user.last_login else "Never",
        "id_status": "VERIFIED" if parent.user.nin_verified else "PENDING_NIN",
        "account_status": _parent_account_status(parent, sub),
    }


TXN_TYPE_MAP = {
    Transaction.MONTHLY_SUB: "MONTHLY_SUB",
    Transaction.EMERGENCY: "EMERGENCY",
    Transaction.TOP_UP: "TOPUP",
    Transaction.REFUND: "REFUND_REQUEST",
}
TXN_STATUS_MAP = {
    Transaction.PAID: "PAID",
    Transaction.FAILED: "FAILED",
    Transaction.PENDING: "PENDING",
    Transaction.REFUNDED: "PAID",
}
METHOD_LABEL = {
    Transaction.CARD: "Card",
    Transaction.BANK_TRANSFER: "Bank Transfer",
    Transaction.WALLET: "Wallet",
}


def serialize_transaction(txn):
    return {
        "id": str(txn.id),
        "parent_name": txn.parent.user.full_name or txn.parent.user.phone,
        "type": TXN_TYPE_MAP.get(txn.payment_type, "MONTHLY_SUB"),
        "amount": float(txn.amount),
        "method": METHOD_LABEL.get(txn.payment_method, txn.payment_method),
        "date": (txn.processed_at or txn.created_at).isoformat(),
        "status": TXN_STATUS_MAP.get(txn.status, "PENDING"),
    }


INCIDENT_TYPE_MAP = {
    Incident.PANIC_ALERT: "PANIC",
    Incident.ROUTE_DEVIATION: "ROUTE_DEVIATION",
    Incident.LATE_PICKUP: "LATE_PICKUP",
    Incident.SICK_CHILD: "SICK_CHILD",
}
SEVERITY_MAP = {
    Incident.CRITICAL: "CRITICAL",
    Incident.MEDIUM: "MEDIUM",
    Incident.LOW: "LOW",
}


def serialize_incident(incident):
    driver_name = None
    if incident.trip_id:
        driver_name = incident.trip.driver.user.full_name
    who = incident.triggered_by.full_name if incident.triggered_by else (driver_name or "Unknown")
    return {
        "id": incident.incident_id,
        "type": INCIDENT_TYPE_MAP.get(incident.incident_type, "ROUTE_DEVIATION"),
        "driver_or_parent": who,
        "description": incident.get_incident_type_display(),
        "severity": SEVERITY_MAP.get(incident.severity, "LOW"),
        "time": incident.created_at.isoformat(),
        "status": "RESOLVED" if incident.status == Incident.RESOLVED else "OPEN",
    }


def serialize_incident_detail(incident):
    driver_name = incident.trip.driver.user.full_name if incident.trip_id else "N/A"
    location = (
        f"{incident.latitude}, {incident.longitude}"
        if incident.latitude is not None and incident.longitude is not None
        else "Unknown"
    )

    rows = list(incident.timeline.select_related("actor").all())
    if not rows:
        timeline = [{"icon": "panic", "title": "Incident reported", "at": incident.created_at.isoformat()}]
    else:
        timeline = []
        for row in rows:
            if row.actor and row.actor.role == CustomUser.Role.ADMIN:
                icon = "admin"
            elif "police" in row.event_text.lower():
                icon = "police"
            else:
                icon = "panic"
            timeline.append({"icon": icon, "title": row.event_text, "at": row.timestamp.isoformat()})

    return {
        **serialize_incident(incident),
        "triggered_by": incident.triggered_by.full_name if incident.triggered_by else "Unknown",
        "driver": driver_name,
        "child": incident.child.full_name if incident.child_id else "N/A",
        "location": location,
        "police_alerted": incident.police_involved,
        "police_alerted_at": None,
        "response_time_min": round(incident.response_time.total_seconds() / 60) if incident.response_time else 0,
        "timeline": timeline,
    }


ZONE_COLORS = ["blue", "green", "orange", "purple"]


def serialize_zone(zone, index):
    return {
        "id": zone.slug,
        "name": zone.name,
        "routes": zone.active_route_count,
        "drivers": zone.driver_count,
        "families": zone.family_count,
        "color": ZONE_COLORS[index % len(ZONE_COLORS)],
        "planned": False,
    }


STOP_STATUS_MAP = {
    Stop.Status.UPCOMING: "upcoming",
    Stop.Status.NEXT: "active",
    Stop.Status.PICKED_UP: "done",
    Stop.Status.DROPPED: "done",
    Stop.Status.NO_SHOW: "done",
}


def serialize_route(trip):
    stops = list(trip.stops.select_related("child").order_by("sequence"))
    return {
        "id": str(trip.id),
        "zone_id": trip.driver.zone.slug if trip.driver.zone else "unassigned",
        "driver_name": trip.driver.user.full_name,
        "stops_count": len(stops),
        "children_count": len(stops),
        "status": "ACTIVE",
        "stops": [
            {
                "sequence": s.sequence,
                "label": s.child.full_name,
                "status": STOP_STATUS_MAP.get(s.status, "upcoming"),
                "time": s.eta.strftime("%H:%M") if s.eta else None,
            }
            for s in stops
        ],
    }


def _trip_fleet_status(trip):
    stops = list(trip.stops.all())
    if any(s.status == Stop.Status.NEXT for s in stops) and not any(
        s.status == Stop.Status.PICKED_UP for s in stops
    ):
        return "PICKUP"
    if any(s.status == Stop.Status.PICKED_UP for s in stops):
        return "DROPOFF"
    return "EN_ROUTE"


def _trip_current_point(trip):
    """Approximate the van's current position from its current/next stop —
    there's no continuous live-location ping model, only one-shot GPS stamped
    on pickup/dropoff, so this tracks the *target* stop rather than a live fix."""
    next_stop = trip.stops.filter(status=Stop.Status.NEXT).select_related("child").first()
    if next_stop and next_stop.child.pickup_point:
        p = next_stop.child.pickup_point
        return {"lat": float(p.y), "lng": float(p.x)}
    last_stop = trip.stops.exclude(status=Stop.Status.UPCOMING).select_related("child").order_by("-sequence").first()
    if last_stop and last_stop.child.pickup_point:
        p = last_stop.child.pickup_point
        return {"lat": float(p.y), "lng": float(p.x)}
    return None


def serialize_fleet_van(trip):
    return {
        "id": str(trip.id),
        "driver_name": trip.driver.user.full_name,
        "plate": trip.driver.plate,
        "status": _trip_fleet_status(trip),
        "point": _trip_current_point(trip),
    }
