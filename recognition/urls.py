from django.urls import path
from .views import home, recognize, get_attendance, download_csv
from .views import register, admin_dashboard, delete_attendance

urlpatterns = [
    path('', home),
    path('recognize/', recognize),
    path('attendance/', get_attendance),
    path('download/', download_csv),
    path('register/', register),
    path('admin-dashboard/', admin_dashboard, name='admin_dashboard'),
    path('delete-attendance/', delete_attendance, name='delete_attendance'),
]