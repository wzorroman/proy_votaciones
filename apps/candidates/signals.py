"""Signals del dominio `candidates` para limpieza de archivos huérfanos.

- `pre_save`: cuando se reemplaza la foto de una ListaCandidatura, borra
  el archivo anterior del storage.
- `post_delete`: cuando se elimina una ListaCandidatura, borra su foto.
"""

import logging

from django.db.models.signals import post_delete, pre_save
from django.dispatch import receiver

from .models import ListaCandidatura

logger = logging.getLogger(__name__)


@receiver(pre_save, sender=ListaCandidatura)
def _borrar_foto_anterior_al_reemplazar(sender, instance, **kwargs):
    """Si cambia el campo `foto`, elimina el archivo previo."""
    if not instance.pk:
        return

    try:
        anterior = ListaCandidatura.objects.get(pk=instance.pk)
    except ListaCandidatura.DoesNotExist:
        return

    foto_vieja = anterior.foto
    foto_nueva = instance.foto

    # Si no había foto antes, nada que borrar
    if not foto_vieja:
        return

    # Si la foto no cambió (mismo nombre), no borrar
    if foto_vieja.name == (foto_nueva.name if foto_nueva else None):
        return

    # Borrar el archivo anterior
    try:
        foto_vieja.delete(save=False)
    except Exception as exc:  # noqa: BLE001
        logger.warning(
            "No se pudo borrar la foto anterior de ListaCandidatura %s: %s",
            instance.pk, exc,
        )


@receiver(post_delete, sender=ListaCandidatura)
def _borrar_foto_al_eliminar(sender, instance, **kwargs):
    """Al eliminar una ListaCandidatura, borra su foto del storage."""
    if not instance.foto:
        return

    try:
        instance.foto.delete(save=False)
    except Exception as exc:  # noqa: BLE001
        logger.warning(
            "No se pudo borrar la foto de ListaCandidatura %s: %s",
            instance.pk, exc,
        )
        