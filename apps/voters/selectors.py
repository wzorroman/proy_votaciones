"""Selectores (queries) del dominio `voters`.

Este módulo es la capa de lectura de electores. NO debe importar nada de
`apps.voting` para evitar importaciones circulares.

- `EstadoElector`: enumeración de estados posibles de un elector frente al voto.
- `proceso_activo()`: proceso electoral activo y no cerrado.
- `electores_habiles(proceso)`: queryset de electores activos y no inhabilitados.
- `listar_padron(...)`: padrón filtrado y paginado (para admin/auditoría).
- `validar_dni(dni, proceso)`: valida un DNI y devuelve (estado, estudiante).
"""

from django.core.paginator import Paginator
from django.db.models import Q

from apps.voters.models import Estudiante, ProcesoElectoral


# ============================================================
#  Estados posibles de un elector
# ============================================================
class EstadoElector:
    OK = "ok"
    NO_EXISTE = "no_existe"
    INHABILITADO = "inhabilitado"
    YA_VOTO = "ya_voto"
    AUSENTE = "ausente"
    PROCESO_CERRADO = "proceso_cerrado"


# ============================================================
#  Proceso electoral
# ============================================================
def proceso_activo():
    """Devuelve el proceso electoral activo y no cerrado, o None."""
    return ProcesoElectoral.objects.filter(activo=True, cerrado=False).first()


# ============================================================
#  Querysets base
# ============================================================
def electores_habiles(proceso):
    """Electores activos y no inhabilitados del proceso."""
    return proceso.estudiantes.filter(es_activo=True, inhabilitado=False)


# ============================================================
#  Padrón paginado (admin / auditoría)
# ============================================================
def listar_padron(proceso, q="", mesa_id=None, estado=None, page=1, per_page=25):
    """Padrón filtrado y paginado.

    Filtros:
      - q         : texto libre (DNI, apellidos, nombres)
      - mesa_id   : id de la mesa
      - estado    : 'emitido' | 'pendiente' | 'ausente' | 'inhabilitado' | None (todos)
    """
    qs = (
        proceso.estudiantes.select_related("mesa", "grado_seccion")
        .order_by("apellido_paterno", "apellido_materno", "nombres")
    )

    if q:
        qs = qs.filter(
            Q(numero_documento__icontains=q)
            | Q(apellido_paterno__icontains=q)
            | Q(apellido_materno__icontains=q)
            | Q(nombres__icontains=q)
        )

    if mesa_id:
        qs = qs.filter(mesa_id=mesa_id)

    if estado == "emitido":
        qs = qs.filter(ha_votado=True)
    elif estado == "pendiente":
        qs = qs.filter(ha_votado=False, fecha_ausentismo__isnull=True)
    elif estado == "ausente":
        qs = qs.filter(fecha_ausentismo__isnull=False)
    elif estado == "inhabilitado":
        qs = qs.filter(inhabilitado=True)
    # estado vacío / None → "Todos": sin filtro adicional (incluye inhabilitados)

    return Paginator(qs, per_page).get_page(page)


# ============================================================
#  Validación de DNI (kiosco)
# ============================================================
def validar_dni(dni: str, proceso) -> tuple[str, Estudiante | None]:
    """Valida un DNI contra el padrón del proceso.

    Devuelve una tupla (estado, estudiante|None):
      - EstadoElector.NO_EXISTE     → el DNI no figura en el padrón.
      - EstadoElector.INHABILITADO  → está desactivado o inhabilitado.
      - EstadoElector.YA_VOTO       → ya emitió su voto.
      - EstadoElector.AUSENTE       → figura como ausente.
      - EstadoElector.OK            → habilitado para votar.
    """
    dni_normalizado = (dni or "").strip()

    estudiante = (
        Estudiante.objects.filter(
            proceso=proceso,
            numero_documento=dni_normalizado,
        )
        .select_related("mesa", "grado_seccion")
        .first()
    )

    if not estudiante:
        return EstadoElector.NO_EXISTE, None

    if not estudiante.es_activo or estudiante.inhabilitado:
        return EstadoElector.INHABILITADO, estudiante

    if estudiante.ha_votado:
        return EstadoElector.YA_VOTO, estudiante

    if estudiante.fecha_ausentismo:
        return EstadoElector.AUSENTE, estudiante

    return EstadoElector.OK, estudiante
