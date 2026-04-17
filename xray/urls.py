# © YAGA Project — Todos los derechos reservados
from django.urls import path
from . import views

app_name = "xray"

urlpatterns = [
    path("", views.index, name="index"),
    path("api/", views.api_datos, name="api_datos"),
]
