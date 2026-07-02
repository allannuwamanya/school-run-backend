# API Sample Data

Here are sample JSON payloads for testing the API endpoints.

## 1. Create Investment Profile

**Endpoint:** `POST /profiles/investment-profiles/`

```json
{
  "user": 1,
  "bio": "Experienced angel investor focused on agri-tech.",
  "philosophy": "Investing in sustainable future.",
  "check_size_range": "5000-10000",
  "investment_type": "technology",
  "linkedin": "https://linkedin.com/in/investor",
  "twitter": "https://twitter.com/investor"
}
```

## 2. Create Business

**Endpoint:** `POST /profiles/businesses/`

```json
{
  "user": 1,
  "name": "Green Future Agro",
  "category": "agriculture",
  "description": "Sustainable farming solutions for modern Africa.",
  "address": "123 Farm Road",
  "city": "Kampala",
  "country": "Uganda",
  "phone": "+256700000000",
  "email": "contact@greenfuture.com",
  "website": "https://greenfuture.com",
  "is_verified": false
}
```

## 3. Create Business Milestone

**Endpoint:** `POST /profiles/milestones/`

```json
{
  "business": 1,
  "title": "Reached 1000 Farmers",
  "description": "Onboarded 1000 farmers to our platform.",
  "date": "2025-10-15"
}
```

## 4. Create Investment Request

**Endpoint:** `POST /profiles/investment-requests/`

```json
{
  "user": 1,
  "business": 1,
  "name": "Seed Round Expansion",
  "type": "equity",
  "amount": "50000000.00",
  "currency": "UGX",
  "description": "Seeking funds to expand to Northern region.",
  "date": "2026-01-01",
  "status": "pending",
  "return_on_investment": "15.00"
}
```

## 5. Record Investment

**Endpoint:** `POST /profiles/investments/`

```json
{
  "investor": 2,
  "request": 1,
  "amount": "10000000.00",
  "description": "Initial tranche.",
  "date": "2026-02-01",
  "status": "approved"
}
```

## 6. Create Community

**Endpoint:** `POST /profiles/communities/`

```json
{
  "name": "Agri-Tech Innovators",
  "description": "A community for tech-enabled agriculture.",
  "people": [1, 2],
  "businesses": [1]
}
```

## 7. Create Job Posting

**Endpoint:** `POST /profiles/job-postings/`

```json
{
  "business": 1,
  "title": "Senior Agronomist",
  "description": "Looking for an experienced agronomist to lead our field team.",
  "location": "Gulu",
  "type": "full_time",
  "salary_range": "2M - 3M UGX",
  "deadline": "2026-03-30",
  "is_active": true
}
```

## 8. Create Job Application

**Endpoint:** `POST /profiles/job-applications/`

```json
{
  "job": 1,
  "applicant": 3,
  "cover_letter": "I am very interested in this position...",
  "status": "pending"
  // Resume file would be handled via multipart/form-data usually
}
```

## 9. Create User (via Accounts App)

**Endpoint:** `POST /user/register` _(Note: Endpoint may vary based on `accounts` app implementation)_

```json
{
  "email": "newuser@example.com",
  "full_name": "New User",
  "password": "securepassword123"
}
```

## 10. Add People to Community

**Endpoint:** `POST /profiles/communities/{id}/add-people/`

```json
{
  "user_ids": [1, 3, 5]
}
```

## 11. Add Businesses to Community

**Endpoint:** `POST /profiles/communities/{id}/add-businesses/`

````json
{
  "business_ids": [2, 4]
}

## 12. Get Current User Profile (with related data)
**Endpoint:** `GET /user/me`
**Header:** `Authorization: Token <your_token>`

```json
{
  "id": 1,
  "full_name": "John Doe",
  "email": "john@example.com",
  "phone": "+256700000000",
  "photo": null,
  "address": "Kampala",
  "created_at": "2026-02-19T10:00:00Z",
  "businesses": [
    {
      "id": 1,
      "name": "Green Future Agro",
      "category": "agriculture",
      ...
    }
  ],
  "investment_profiles": [],
  "job_applications": [],
  "communities": []
}
````

```

```
