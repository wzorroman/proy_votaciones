from django.conf import settings
from django.db import models

from apps.core.models import TimeStampedModel


class AccionAdministrativa(TimeStampedModel):
    usuario = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True)
    accion = models.CharField(max_length=80)
    entidad = models.CharField(max_length=120, blank=True)
    entidad_id = models.PositiveIntegerField(null=True, blank=True)
    detalle = models.JSONField(default=dict, blank=True)
    ip = models.GenericIPAddressField(null=True, blank=True)

    def __str__(self):
        return f"{self.accion} - {self.usuario or 'Sistema'}"
