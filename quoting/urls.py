from django.urls import path

from quoting.views import desk

urlpatterns = [
    path("", desk, name="ny-auto-quote"),
]
