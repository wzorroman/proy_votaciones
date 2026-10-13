import os
import uuid

from django.core.validators import FileExtensionValidator
from django.db import models

from apps.core.models import TimeStampedModel


# ============================================================
#  Helpers
# ============================================================
def _foto_upload_path(instance, filename):
    """Ruta única para la foto de una lista: media/listas/<tipo_id>/<uuid>.<ext>."""
    ext = os.path.splitext(filename)[1].lower()
    tipo_id = instance.tipo_eleccion_id or "sin_tipo"
    return f"listas/tipo_{tipo_id}/{uuid.uuid4().hex}{ext}"

# ============================================================
#  Modelos
# ============================================================
class TipoEleccion(TimeStampedModel):
    proceso = models.ForeignKey("voters.ProcesoElectoral", on_delete=models.CASCADE, related_name="tipos_eleccion")
    nombre = models.CharField(max_length=80)
    orden_aparicion = models.PositiveIntegerField(default=1)
    es_activo = models.BooleanField(default=True)
    color_fondo = models.CharField(max_length=30, default="#EAF3FF")

    class Meta:
        ordering = ["orden_aparicion", "id"]

    def __str__(self):
        #return f"{self.proceso.nombre} - {self.nombre}"
        return f"{self.nombre}"


class ListaCandidatura(TimeStampedModel):
    proceso = models.ForeignKey("voters.ProcesoElectoral", on_delete=models.CASCADE, related_name="listas")
    tipo_eleccion = models.ForeignKey(TipoEleccion, on_delete=models.CASCADE, related_name="listas")
    nombre = models.CharField(max_length=120)
    descripcion = models.CharField(max_length=200, blank=True)
    es_activo = models.BooleanField(default=True)

    # ---------- Imagen de la lista ----------
    foto = models.ImageField(
        upload_to=_foto_upload_path,
        blank=True,
        null=True,
        verbose_name="Foto / símbolo de la lista",
        help_text="PNG o JPG. Máximo 3 MB. Recomendado: 800x800 px (cuadrada).",
        validators=[
            FileExtensionValidator(allowed_extensions=["png", "jpg", "jpeg"]),
        ],
    )
    
    class Meta:
        ordering = ["tipo_eleccion__orden_aparicion", "nombre"]

    def __str__(self):
        # return f"{self.tipo_eleccion.nombre} - {self.nombre}"
        return f"{self.nombre}"
