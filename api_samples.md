# SchoolRun API — Sample Payloads

Here are sample JSON payloads for testing the SchoolRun database and backend API endpoints.

---

## 1. Register a User (Parent or Driver)

**Endpoint:** `POST /user/register`

```json
{
  "email": "amara.johnson@example.com",
  "full_name": "Amara Johnson",
  "phone": "+2348012345678",
  "password": "SecurePassword123!",
  "role": "parent"
}
```

---

## 2. Parent Profile Setup & Preferences

**Endpoint:** `PATCH /user/me/` (or update user details)

```json
{
  "nin_verified": true,
  "push_notifications_enabled": true,
  "location_sharing_enabled": true,
  "dark_mode": false
}
```

---

## 3. Create a Child Profile

**Endpoint:** `POST /api/children/`

```json
{
  "full_name": "Maya Johnson",
  "age": 8,
  "gender": "female",
  "blood_type": "O+",
  "class_grade": "Grade 3",
  "school_name": "Greenfield Academy, Lagos",
  "allergy_notes": "Peanut Allergy",
  "pickup_instructions": "Gate Code: 1234. Ring bell."
}
```

---

## 4. Setup Child Schedule

**Endpoint:** `POST /api/children/{child_uuid}/schedule/`

```json
{
  "apply_to_all_children": true,
  "morning_dropoff_time": "07:00:00",
  "afternoon_pickup_time": "16:00:00",
  "monday": true,
  "tuesday": true,
  "wednesday": true,
  "thursday": true,
  "friday": true,
  "saturday": false,
  "sunday": false
}
```

---

## 5. Add Child Pickup Location

**Endpoint:** `POST /api/children/{child_uuid}/pickup-locations/`

```json
{
  "address": "14 Adeola Close, Lekki Phase 1, Lagos",
  "latitude": 6.4281,
  "longitude": 3.4219,
  "is_primary": true
}
```

---

## 6. Driver Onboarding Progress & Vehicle Setup

**Endpoint:** `POST /api/drivers/onboarding/vehicle/`

```json
{
  "model": "Toyota Hiace (Silver)",
  "color": "Silver",
  "plate": "LSD 342 QX",
  "capacity": 9
}
```

---

## 7. Driver Document Status Check / Review (Admin Panel API)

**Endpoint:** `PATCH /api/drivers/documents/{doc_id}/`

```json
{
  "status": "verified",
  "notes": "Driver license looks clear and valid until 2029."
}
```

---

## 8. Dispatch/Trip Log Creation

**Endpoint:** `POST /api/trips/`

```json
{
  "route_id": "RT-001",
  "trip_type": "standard",
  "date": "2026-07-02",
  "distance_km": 15.6,
  "price": 2500.00,
  "status": "scheduled"
}
```

---

## 9. Stop Status Update (Driver App)

**Endpoint:** `PATCH /api/stops/{stop_id}/`

```json
{
  "status": "picked_up",
  "actual_arrival": "2026-07-02T07:15:00Z"
}
```

---

## 10. Trigger a Critical Incident (Panic Alert)

**Endpoint:** `POST /api/incidents/`

```json
{
  "incident_type": "panic_alert",
  "severity": "critical",
  "trip": 42,
  "child": 12,
  "latitude": 6.4312,
  "longitude": 3.4278,
  "police_involved": true,
  "resolution_notes": "Panic button pressed by parent. Driver verified false alarm, child was safely inside school gates."
}
```

---

## 11. Subscription Plan Billing & Transactions

**Endpoint:** `POST /api/payments/transactions/`

```json
{
  "transaction_id": "TXN-984372981-L",
  "payment_type": "monthly_sub",
  "amount": 25000.00,
  "payment_method": "card",
  "status": "paid",
  "reference": "pstk_pay_8493028471"
}
```
