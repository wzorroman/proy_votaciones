import os
import uuid

from django.db import models
from django.core.validators import FileExtensionValidator

from apps.core.models import TimeStampedModel, UUIDModel


def _logo_upload_path(instance, filename):
    """Genera una ruta única: media/logos/<proceso_id>/<uuid>.<ext>."""
    ext = os.path.splitext(filename)[1].lower()
    return f"logos/proceso_{instance.pk or 'nuevo'}/{uuid.uuid4().hex}{ext}"

class ProcesoElectoral(TimeStampedModel):
    nombre = models.CharField(max_length=120)
    activo = models.BooleanField(default=True)
    cerrado = models.BooleanField(default=False)
    votacion_iniciada = models.BooleanField(
        default=False,
        verbose_name="Votación iniciada",
        help_text="Se activa al pulsar «Iniciar votación»; hasta entonces el kiosco permanece bloqueado.",
    )
    votacion_pausada = models.BooleanField(
        default=False,
        verbose_name="Votación en pausa",
        help_text="Se activa al pulsar «Pausar»; el kiosco queda bloqueado temporalmente hasta reanudar.",
    )
    fecha_inicio = models.DateTimeField(null=True, blank=True)
    fecha_cierre = models.DateTimeField(null=True, blank=True)
    habilitar_voto_nulo = models.BooleanField(default=False)
    habilitar_voto_invalido = models.BooleanField(default=False)
    # ---------- Marca / identidad visual ----------
    logo = models.ImageField(
        upload_to=_logo_upload_path,
        blank=True,
        null=True,
        verbose_name="Logo institucional",
        help_text="PNG, JPG o JPEG. Máximo 5 MB. Recomendado: fondo transparente.",
        validators=[
            FileExtensionValidator(allowed_extensions=["png", "jpg", "jpeg"]),
        ],
    )
    nombre_institucion = models.CharField(
        max_length=200,
        blank=True,
        verbose_name="Nombre de la institución",
        help_text="Se muestra arriba del logo. Ej: COLEGIO NACIONAL EMBLEMÁTICO",
    )

    def __str__(self):
        return self.nombre


class MesaDeVotacion(TimeStampedModel):
    proceso = models.ForeignKey(ProcesoElectoral, on_delete=models.CASCADE, related_name="mesas")
    numero_mesa = models.CharField(max_length=50)
    descripcion = models.CharField(max_length=200, blank=True)
    es_activo = models.BooleanField(default=True)

    def __str__(self):
        #return f"{self.proceso.nombre} - {self.numero_mesa}"
        return f"{self.numero_mesa}"


class GradoSeccion(TimeStampedModel):
    """Catálogo global de grado/sección (categorización de estudiantes).

    El ``nivel`` es opcional y se normaliza a minúsculas. Los grados y
    secciones se administran una sola vez (globalmente) y se reutilizan en
    todos los procesos electorales.
    """

    nivel = models.CharField(max_length=20, blank=True, verbose_name="Nivel")
    grado = models.CharField(max_length=20, verbose_name="Grado")
    seccion = models.CharField(max_length=10, verbose_name="Sección")
    orden = models.PositiveSmallIntegerField(
        default=0,
        help_text="Orden de presentación (1 = primer grado).",
    )
    es_activo = models.BooleanField(default=True)

    class Meta:
        ordering = ["nivel", "orden", "grado", "seccion"]
        constraints = [
            models.UniqueConstraint(
                fields=["nivel", "grado", "seccion"],
                name="unique_nivel_grado_seccion",
            )
        ]
        verbose_name = "Grado y sección"
        verbose_name_plural = "Grados y secciones"

    def save(self, *args, **kwargs):
        self.nivel = (self.nivel or "").strip().lower()
        self.grado = (self.grado or "").strip()
        self.seccion = (self.seccion or "").strip().upper()
        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.grado} {self.seccion}".strip()


class Estudiante(TimeStampedModel, UUIDModel):
    proceso = models.ForeignKey(ProcesoElectoral, on_delete=models.CASCADE, related_name="estudiantes")
    mesa = models.ForeignKey(MesaDeVotacion, on_delete=models.SET_NULL, null=True, blank=True, related_name="estudiantes")
    grado_seccion = models.ForeignKey(
        GradoSeccion,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="estudiantes",
        verbose_name="Grado y sección",
    )
    numero_documento = models.CharField(max_length=20, unique=True)
    apellido_paterno = models.CharField(max_length=80, blank=True)
    apellido_materno = models.CharField(max_length=80, blank=True)
    nombres = models.CharField(max_length=120, blank=True)
    es_activo = models.BooleanField(default=True)
    inhabilitado = models.BooleanField(default=False)
    ha_votado = models.BooleanField(default=False)
    fecha_ausentismo = models.DateTimeField(null=True, blank=True)
    fecha_inhabilitacion = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["apellido_paterno", "apellido_materno", "nombres"]

    def __str__(self):
        return f"{self.nombres} {self.apellido_paterno} {self.apellido_materno} - {self.numero_documento}"
