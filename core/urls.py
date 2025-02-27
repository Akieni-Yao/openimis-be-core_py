from core import views
from django.urls import include, path
from rest_framework.routers import DefaultRouter

router = DefaultRouter()
router.register(r'users', views.UserViewSet)

urlpatterns = [
    path('', include(router.urls)),
    path('fetch_export', views.fetch_export),
    path('scheduled_jobs', views.get_scheduled_jobs),
    # To delete later
    path('force_verify_user', views.force_verify_user),
    path('force_un_verify_user', views.force_un_verify_user),
]
