# © YAGA Project — Todos los derechos reservados
from django.urls import path
from . import views

app_name = "xray"

urlpatterns = [
    path("", views.index, name="index"),
    path("api/tendencia/", views.api_tendencia, name="api_tendencia"),
]
