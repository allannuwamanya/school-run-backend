from django.urls import path
from rest_framework_simplejwt.views import TokenRefreshView

from . import views

urlpatterns = [
    # Existing JWT endpoints
    path('login/', views.LoginView.as_view(), name='token_obtain_pair'),
    path('login/refresh/', TokenRefreshView.as_view(), name='token_refresh'),
    # Auth (contract paths)
    path('auth/register', views.RegisterView.as_view(), name='auth-register'),
    path('auth/login', views.LoginView.as_view(), name='auth-login'),
    path('auth/refresh', TokenRefreshView.as_view(), name='auth-refresh'),
    # Account
    path('me', views.MeView.as_view(), name='api-me'),
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
    # Stops
    path('stops/<uuid:pk>/pickup', views.StopPickupView.as_view(), name='api-stop-pickup'),
    path('stops/<uuid:pk>/dropoff', views.StopDropoffView.as_view(), name='api-stop-dropoff'),
    path('stops/<uuid:pk>/no-show', views.StopNoShowView.as_view(), name='api-stop-noshow'),
    # History
    path('history', views.HistoryView.as_view(), name='api-history'),
    # Notifications
    path('notifications', views.NotificationListView.as_view(), name='api-notifications'),
    path('notifications/read', views.NotificationReadView.as_view(), name='api-notifications-read'),
    # Devices
    path('devices', views.DeviceRegisterView.as_view(), name='api-devices'),
]
