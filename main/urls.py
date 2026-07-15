"""base_project URL Configuration

The `urlpatterns` list routes URLs to views. For more information please see:
    https://docs.djangoproject.com/en/3.0/topics/http/urls/
Examples:
Function views
    1. Add an import:  from my_app import views
    2. Add a URL to urlpatterns:  path('', views.home, name='home')
Class-based views
    1. Add an import:  from other_app.views import Home
    2. Add a URL to urlpatterns:  path('', Home.as_view(), name='home')
Including another URLconf
    1. Import the include() function: from django.urls import include, path
    2. Add a URL to urlpatterns:  path('blog/', include('blog.urls'))
"""
from django.urls import path, include

from rest_framework import permissions
from drf_yasg.views import get_schema_view
from drf_yasg import openapi
from django.conf.urls.static import static
from main import settings
from . import views, health


schema_view = get_schema_view(
    openapi.Info(
        title="SchoolRun API",
        default_version='v1',
        description="SchoolRun Backend API — school transport management platform.",
        contact=openapi.Contact(email="dev@schoolrun.ng"),
        license=openapi.License(name="Proprietary"),
    ),
    public=True,
    permission_classes=(permissions.AllowAny,),
)


urlpatterns = [
    path('', views.index),
    # path('swagger(?P<format>\.json|\.yaml)', schema_view.without_ui(cache_timeout=0), name='schema-json'),
    path('swagger/', schema_view.with_ui('swagger', cache_timeout=0), name='schema-swagger-ui'),
    path('redoc', schema_view.with_ui('redoc', cache_timeout=0), name='schema-redoc'),
    # Django admin removed — /admin/* belongs to the React ops console (served
    # by the frontend container), so nginx no longer proxies /admin to Django.
    path('user/', include('accounts.urls')),
    path('api/', include('api.urls')),
    path('health/', health.HealthCheckView.as_view(), name='health'),
    path('ready/', health.ReadyCheckView.as_view(), name='ready'),
  ]

if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)