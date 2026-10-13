import uuid

from django.db import models

from apps.core.models import TimeStampedModel


class Voto(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    proceso = models.ForeignKey("voters.ProcesoElectoral", on_delete=models.CASCADE, related_name="votos")
    tipo_eleccion = models.ForeignKey("candidates.TipoEleccion", on_delete=models.CASCADE, related_name="votos")
    lista = models.ForeignKey("candidates.ListaCandidatura", on_delete=models.CASCADE, related_name="votos")
    boleta_id = models.UUIDField(null=True, blank=True)

    class Meta:
        indexes = [models.Index(fields=["proceso", "tipo_eleccion", "lista"])]

    def __str__(self):
        return f"Voto {self.id} - {self.lista}"


class RegistroParticipacion(TimeStampedModel):
    proceso = models.ForeignKey("voters.ProcesoElectoral", on_delete=models.CASCADE, related_name="participaciones")
    estudiante = models.ForeignKey("voters.Estudiante", on_delete=models.CASCADE, related_name="participaciones")
    hash_integridad = models.CharField(max_length=128)
    boleta_cifrada = models.TextField(null=True, blank=True)

    class Meta:
        unique_together = ("proceso", "estudiante")

    def __str__(self):
        return f"Participacion {self.estudiante}"


class ActaCierreProceso(TimeStampedModel):
    proceso = models.OneToOneField("voters.ProcesoElectoral", on_delete=models.CASCADE, related_name="acta")
    total_electores_habiles = models.PositiveIntegerField(default=0)
    total_votos_emitidos = models.PositiveIntegerField(default=0)
    total_ausentes = models.PositiveIntegerField(default=0)
    resultados_consolidados = models.JSONField(default=dict)
    fecha_cierre_oficial = models.DateTimeField()

    def __str__(self):
        return f"Acta - {self.proceso.nombre}"
