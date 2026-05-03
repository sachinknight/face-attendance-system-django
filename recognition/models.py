from django.db import models
from django.utils.timezone import localdate


# Create your models here.

class Subject(models.Model):
    name = models.CharField(max_length=100)

    def __str__(self):
        return self.name


class Person(models.Model):
    name = models.CharField(max_length=100)

    def __str__(self):
        return self.name


class Attendance(models.Model):
    person = models.ForeignKey(Person, on_delete=models.CASCADE)
    subject = models.ForeignKey(Subject, on_delete=models.CASCADE, null=True, blank=True)
    timestamp = models.DateTimeField(auto_now_add=True)
    date = models.DateField(default=localdate)
    status = models.CharField(max_length=10, default="IN")  # IN / OUT

    def __str__(self):
        return f"{self.person.name} - {self.status} - {self.timestamp}"