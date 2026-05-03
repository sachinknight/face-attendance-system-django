

# Register your models here.
from django.contrib import admin
from .models import Person, Attendance

admin.site.register(Person)
admin.site.register(Attendance)