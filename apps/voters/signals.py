"""Signals del dominio `voters` para limpieza del logo del proceso."""

import logging

from django.db.models.signals import post_delete, pre_save
from django.dispatch import receiver

from .models import ProcesoElectoral

logger = logging.getLogger(__name__)


@receiver(pre_save, sender=ProcesoElectoral)
def _borrar_logo_anterior_al_reemplazar(sender, instance, **kwargs):
    if not instance.pk:
        return

    try:
        anterior = ProcesoElectoral.objects.get(pk=instance.pk)
    except ProcesoElectoral.DoesNotExist:
        return

    logo_viejo = anterior.logo
    logo_nuevo = instance.logo

    if not logo_viejo:
        return

    if logo_viejo.name == (logo_nuevo.name if logo_nuevo else None):
        return

    try:
        logo_viejo.delete(save=False)
    except Exception as exc:  # noqa: BLE001
        logger.warning(
            "No se pudo borrar el logo anterior del proceso %s: %s",
            instance.pk, exc,
        )


@receiver(post_delete, sender=ProcesoElectoral)
def _borrar_logo_al_eliminar(sender, instance, **kwargs):
    if not instance.logo:
        return

    try:
        instance.logo.delete(save=False)
    except Exception as exc:  # noqa: BLE001
        logger.warning(
            "No se pudo borrar el logo del proceso %s: %s",
            instance.pk, exc,
        )
