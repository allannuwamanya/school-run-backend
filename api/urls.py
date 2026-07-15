from django.urls import path
from rest_framework_simplejwt.views import TokenRefreshView

from . import admin_views, views

urlpatterns = [
    # Existing JWT endpoints
    path('login/', views.LoginView.as_view(), name='token_obtain_pair'),
    path('login/refresh/', TokenRefreshView.as_view(), name='token_refresh'),
    # Auth (contract paths)
    path('auth/register', views.RegisterView.as_view(), name='auth-register'),
    path('auth/login', views.LoginView.as_view(), name='auth-login'),
    path('auth/google', views.GoogleLoginView.as_view(), name='auth-google'),
    path('auth/refresh', TokenRefreshView.as_view(), name='auth-refresh'),
    # Account
    path('me', views.MeView.as_view(), name='api-me'),
    path('me/change-password', views.MeChangePasswordView.as_view(), name='api-me-change-password'),
    # Schools
    path('schools', views.SchoolListView.as_view(), name='api-schools'),
    # Children
    path('children', views.ChildListCreateView.as_view(), name='api-children'),
    path('children/<uuid:pk>', views.ChildDetailView.as_view(), name='api-child-detail'),
    path('children/<uuid:pk>/schedule', views.ChildScheduleView.as_view(), name='api-child-schedule'),
    # Parent dashboard
    path('dashboard', views.DashboardView.as_view(), name='api-dashboard'),
    path('parent/driver', views.ParentDriverView.as_view(), name='api-parent-driver'),
    # Driver
    path('driver/manifest', views.DriverManifestView.as_view(), name='api-driver-manifest'),
    path('driver/trips/<uuid:pk>/start', views.TripStartView.as_view(), name='api-trip-start'),
    path('driver/trips/<uuid:pk>/complete', views.TripCompleteView.as_view(), name='api-trip-complete'),
    path('driver/location', views.DriverLocationPingView.as_view(), name='api-driver-location'),
    # Stops
    path('stops/<uuid:pk>', views.StopDetailView.as_view(), name='api-stop-detail'),
    path('stops/<uuid:pk>/pickup', views.StopPickupView.as_view(), name='api-stop-pickup'),
    path('stops/<uuid:pk>/dropoff', views.StopDropoffView.as_view(), name='api-stop-dropoff'),
    path('stops/<uuid:pk>/no-show', views.StopNoShowView.as_view(), name='api-stop-noshow'),
    # Incidents (self-report — non-panic unhappy-path escalation)
    path('incidents', views.IncidentReportView.as_view(), name='api-incidents'),
    # History
    path('history', views.HistoryView.as_view(), name='api-history'),
    # Notifications
    path('notifications', views.NotificationListView.as_view(), name='api-notifications'),
    path('notifications/read', views.NotificationReadView.as_view(), name='api-notifications-read'),
    path('notifications/<uuid:pk>', views.NotificationDetailView.as_view(), name='api-notification-detail'),
    # Devices
    path('devices', views.DeviceRegisterView.as_view(), name='api-devices'),

    # Admin console
    path('admin/overview', admin_views.AdminOverviewView.as_view(), name='admin-overview'),
    path('admin/drivers', admin_views.AdminDriverListView.as_view(), name='admin-drivers'),
    path('admin/drivers/<uuid:pk>', admin_views.AdminDriverDetailView.as_view(), name='admin-driver-detail'),
    path('admin/drivers/<uuid:pk>/approve', admin_views.AdminDriverApproveView.as_view(), name='admin-driver-approve'),
    path('admin/drivers/<uuid:pk>/reject', admin_views.AdminDriverRejectView.as_view(), name='admin-driver-reject'),
    path(
        'admin/drivers/<uuid:pk>/request-docs',
        admin_views.AdminDriverRequestDocsView.as_view(),
        name='admin-driver-request-docs',
    ),
    path(
        'admin/drivers/<uuid:pk>/documents',
        admin_views.AdminDriverDocumentUploadView.as_view(),
        name='admin-driver-document-upload',
    ),
    path(
        'admin/drivers/<uuid:pk>/nin-number',
        admin_views.AdminDriverUpdateNinNumberView.as_view(),
        name='admin-driver-nin-number',
    ),
    path(
        'admin/drivers/<uuid:pk>/verify-nin',
        admin_views.AdminDriverVerifyNinView.as_view(),
        name='admin-driver-verify-nin',
    ),
    path(
        'admin/drivers/<uuid:pk>/reject-nin',
        admin_views.AdminDriverRejectNinView.as_view(),
        name='admin-driver-reject-nin',
    ),
    path('admin/parents', admin_views.AdminParentListView.as_view(), name='admin-parents'),
    path('admin/parents/<uuid:pk>', admin_views.AdminParentDetailView.as_view(), name='admin-parent-detail'),
    path('admin/parents/<uuid:pk>/suspend', admin_views.AdminParentSuspendView.as_view(), name='admin-parent-suspend'),
    path(
        'admin/parents/<uuid:pk>/assign-driver',
        admin_views.AdminParentAssignDriverView.as_view(),
        name='admin-parent-assign-driver',
    ),
    path(
        'admin/parents/<uuid:pk>/unassign-driver',
        admin_views.AdminParentUnassignDriverView.as_view(),
        name='admin-parent-unassign-driver',
    ),
    path(
        'admin/parents/<uuid:pk>/verify-nin',
        admin_views.AdminParentVerifyNinView.as_view(),
        name='admin-parent-verify-nin',
    ),
    path(
        'admin/parents/<uuid:pk>/reject-nin',
        admin_views.AdminParentRejectNinView.as_view(),
        name='admin-parent-reject-nin',
    ),
    path('admin/zones', admin_views.AdminZoneListView.as_view(), name='admin-zones'),
    path('admin/dispatch', admin_views.AdminDispatchView.as_view(), name='admin-dispatch'),
    path('admin/dispatch/emergency', admin_views.AdminEmergencyDispatchView.as_view(), name='admin-dispatch-emergency'),
    path('admin/dispatch/<uuid:trip_id>/trail', admin_views.AdminDriverTrailView.as_view(), name='admin-dispatch-trail'),
    path('admin/payments', admin_views.AdminPaymentsView.as_view(), name='admin-payments'),
    path(
        'admin/payments/<uuid:pk>/refund',
        admin_views.AdminRefundTransactionView.as_view(),
        name='admin-payments-refund',
    ),
    path('admin/incidents', admin_views.AdminIncidentListView.as_view(), name='admin-incidents'),
    path(
        'admin/incidents/<str:incident_id>/resolve',
        admin_views.AdminIncidentResolveView.as_view(),
        name='admin-incidents-resolve',
    ),
    path('admin/analytics', admin_views.AdminAnalyticsView.as_view(), name='admin-analytics'),
    path('admin/audit', admin_views.AdminAuditLogView.as_view(), name='admin-audit'),
    path('admin/staff', admin_views.AdminStaffListView.as_view(), name='admin-staff'),
    path('admin/staff/<int:pk>', admin_views.AdminStaffDeleteView.as_view(), name='admin-staff-delete'),
    path('admin/staff/<int:pk>/toggle', admin_views.AdminStaffToggleView.as_view(), name='admin-staff-toggle'),
    path('admin/users', admin_views.AdminUserListView.as_view(), name='admin-users'),
    path(
        'admin/users/<int:pk>/set-password',
        admin_views.AdminUserSetPasswordView.as_view(),
        name='admin-user-set-password',
    ),
    path('admin/users/<int:pk>', admin_views.AdminUserDeleteView.as_view(), name='admin-user-delete'),
]
