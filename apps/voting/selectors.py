"""Selectores (queries) del dominio `voting`.

Este módulo es la capa de lectura para todo lo relacionado con métricas
del panel, participación por mesa y filtros del padrón en la vista de
Auditoría.

Depende de `apps.voters.selectors.electores_habiles` (queryset base de
electores activos y no inhabilitados).
"""

from django.db.models import Count, Q

from apps.voters.selectors import electores_habiles


# Filtro reutilizable para "elector hábil" desde el lado de la mesa.
HABIL = Q(estudiantes__es_activo=True, estudiantes__inhabilitado=False)


# ============================================================
#  Métricas del dashboard
# ============================================================
def metricas_generales(proceso):
    """Devuelve un dict con las métricas globales del proceso.

    Retorna:
        {
            "habiles":    int,
            "emitidos":   int,
            "faltantes":  int,
            "porcentaje": float,  # redondeado a 1 decimal
        }
    """
    qs = electores_habiles(proceso)
    habiles = qs.count()
    emitidos = qs.filter(ha_votado=True).count()
    faltantes = habiles - emitidos
    porcentaje = round((emitidos / habiles * 100), 1) if habiles else 0.0

    return {
        "habiles": habiles,
        "emitidos": emitidos,
        "faltantes": faltantes,
        "porcentaje": porcentaje,
    }


# Filtro de elector hábil usado en las agregaciones del dashboard.
HABIL_ESTUDIANTE = Q(es_activo=True, inhabilitado=False)


def participacion_por_grado_seccion(proceso):
    """Participación agregada por grado y desglosada por grado+sección.

    Retorna:
        {
            "grados":    [ { "nivel", "grado", "habiles", "emitidos", "porcentaje" }, ... ],
            "secciones": [ { "nivel", "grado", "seccion", "habiles", "emitidos",
                             "porcentaje" }, ... ],
        }

    Orden: nivel → orden de grado → grado → sección.
    """
    filas = list(
        proceso.estudiantes
        .exclude(grado_seccion__isnull=True)
        .values(
            "grado_seccion__nivel",
            "grado_seccion__grado",
            "grado_seccion__seccion",
        )
        .annotate(
            habiles=Count("id", filter=HABIL_ESTUDIANTE),
            emitidos=Count("id", filter=HABIL_ESTUDIANTE & Q(ha_votado=True)),
        )
        .order_by(
            "grado_seccion__nivel",
            "grado_seccion__orden",
            "grado_seccion__grado",
            "grado_seccion__seccion",
        )
    )

    grados = {}
    secciones = []
    for fila in filas:
        nivel = fila["grado_seccion__nivel"]
        grado = fila["grado_seccion__grado"]
        seccion = fila["grado_seccion__seccion"]
        habiles = fila["habiles"]
        emitidos = fila["emitidos"]

        g = grados.setdefault(
            (nivel, grado),
            {"nivel": nivel, "grado": grado, "habiles": 0, "emitidos": 0},
        )
        g["habiles"] += habiles
        g["emitidos"] += emitidos

        secciones.append({
            "nivel": nivel,
            "grado": grado,
            "seccion": seccion,
            "habiles": habiles,
            "emitidos": emitidos,
            "porcentaje": round(emitidos / habiles * 100, 1) if habiles else 0.0,
        })

    lista_grados = [
        {
            "nivel": g["nivel"],
            "grado": g["grado"],
            "habiles": g["habiles"],
            "emitidos": g["emitidos"],
            "porcentaje": round(g["emitidos"] / g["habiles"] * 100, 1) if g["habiles"] else 0.0,
        }
        for g in grados.values()  # preserva el orden de inserción
    ]

    return {"grados": lista_grados, "secciones": secciones}


def desglose_grado_seccion_por_mesa(proceso):
    """Detalle de grados y secciones por mesa, con cantidades de hábiles.

    Retorna una lista de dicts:
        [
            {
                "id": int,
                "numero_mesa": str,
                "descripcion": str,
                "habiles": int,   # total de hábiles en la mesa
                "filas": [ { "grado", "seccion", "cantidad" }, ... ],
            }, ...
        ]

    Solo se incluyen mesas con al menos un estudiante hábil. Orden:
    mesa → nivel → orden de grado → grado → sección.
    """
    filas = list(
        proceso.estudiantes
        .exclude(mesa__isnull=True)
        .exclude(grado_seccion__isnull=True)
        .values(
            "mesa__id",
            "mesa__numero_mesa",
            "mesa__descripcion",
            "grado_seccion__nivel",
            "grado_seccion__grado",
            "grado_seccion__seccion",
        )
        .annotate(cantidad=Count("id", filter=HABIL_ESTUDIANTE))
        .filter(cantidad__gt=0)
        .order_by(
            "mesa__numero_mesa",
            "grado_seccion__nivel",
            "grado_seccion__orden",
            "grado_seccion__grado",
            "grado_seccion__seccion",
        )
    )

    por_mesa = {}
    for fila in filas:
        mesa_id = fila["mesa__id"]
        mesa = por_mesa.setdefault(mesa_id, {
            "id": mesa_id,
            "numero_mesa": fila["mesa__numero_mesa"],
            "descripcion": fila["mesa__descripcion"],
            "habiles": 0,
            "filas": [],
        })
        mesa["habiles"] += fila["cantidad"]
        mesa["filas"].append({
            "grado": fila["grado_seccion__grado"],
            "seccion": fila["grado_seccion__seccion"],
            "cantidad": fila["cantidad"],
        })

    return [m for m in por_mesa.values() if m["habiles"]]


def participacion_por_mesa(proceso):
    """Lista de mesas con su conteo de hábiles y emitidos.

    Retorna una lista de dicts:
        [
            {
                "numero_mesa": "Mesa 1",
                "descripcion": "Aula 102",
                "habiles": 400,
                "emitidos": 320,
            },
            ...
        ]
    """
    
    return list(
        proceso.mesas.annotate(
            habiles=Count("estudiantes", filter=HABIL),
            emitidos=Count(
                "estudiantes",
                filter=HABIL & Q(estudiantes__ha_votado=True),
            ),
        )
        .order_by("numero_mesa")
        .values("id", "numero_mesa", "descripcion", "habiles", "emitidos")
    )


# ============================================================
#  Consultas para el módulo de Auditoría de Padrón
# ============================================================
def lista_mesas(proceso):
    """Mesas del proceso para poblar el <select> de filtro."""
    return list(
        proceso.mesas
        .order_by("numero_mesa")
        .values("id", "numero_mesa", "descripcion")
    )


def lista_niveles(proceso):
    """Niveles distintos presentes en el padrón del proceso."""
    return list(
        proceso.estudiantes
        .exclude(grado_seccion__isnull=True)
        .exclude(grado_seccion__nivel="")
        .values_list("grado_seccion__nivel", flat=True)
        .distinct()
        .order_by("grado_seccion__nivel")
    )


def lista_grados(proceso, nivel=None):
    """Grados distintos, opcionalmente filtrados por nivel."""
    qs = proceso.estudiantes.exclude(grado_seccion__isnull=True)
    if nivel:
        qs = qs.filter(grado_seccion__nivel=nivel)
    return list(
        qs.values_list("grado_seccion__grado", flat=True)
        .distinct()
        .order_by("grado_seccion__orden", "grado_seccion__grado")
    )


def lista_secciones(proceso, nivel=None, grado=None):
    """Secciones distintas, opcionalmente filtradas por nivel y grado."""
    qs = proceso.estudiantes.exclude(grado_seccion__isnull=True)
    if nivel:
        qs = qs.filter(grado_seccion__nivel=nivel)
    if grado:
        qs = qs.filter(grado_seccion__grado=grado)
    return list(
        qs.values_list("grado_seccion__seccion", flat=True)
        .distinct()
        .order_by("grado_seccion__seccion")
    )


def resumen_asignacion_mesas(proceso):
    """Resumen de asignación de mesas del padrón.

    Retorna:
        {
            "total": int,       # total de estudiantes del proceso
            "asignados": int,   # estudiantes con mesa
            "sin_mesa": int,    # estudiantes sin mesa
            "porcentaje": float,# % de asignación (1 decimal)
        }
    """
    total = proceso.estudiantes.count()
    sin_mesa = proceso.estudiantes.filter(mesa__isnull=True).count()
    asignados = total - sin_mesa
    porcentaje = round((asignados / total * 100), 1) if total else 0.0
    return {
        "total": total,
        "asignados": asignados,
        "sin_mesa": sin_mesa,
        "porcentaje": porcentaje,
    }


def proceso_sin_votantes_asignados(proceso):
    """True si el proceso NO tiene ningún votante asignado a una mesa.

    Se usa para evitar que el proceso quede "en marcha" sin datos válidos
    (por ejemplo, al crearlo de cero desde el admin sin importar padrón).
    """
    if proceso is None:
        return True
    return not proceso.estudiantes.filter(mesa__isnull=False).exists()


def estudiantes_sin_mesa(proceso):
    """Queryset de estudiantes sin mesa asignada."""
    return (
        proceso.estudiantes
        .filter(mesa__isnull=True)
        .order_by("apellido_paterno", "apellido_materno", "nombres")
    )


# ============================================================
#  Reporte de padrón por mesas (PDF)
# ============================================================
_ORDEN_PADRON = (
    "grado_seccion__nivel",
    "grado_seccion__orden",
    "grado_seccion__grado",
    "grado_seccion__seccion",
    "apellido_paterno",
    "apellido_materno",
    "nombres",
)


def _nombre_completo(est):
    """'APELLIDO PATERNO APELLIDO MATERNO, NOMBRES' (formato padrón)."""
    return (
        f"{est.apellido_paterno} {est.apellido_materno}, {est.nombres}"
    ).strip(", ")


def _filas_padron(estudiantes):
    """Filas del padrón numeradas y con banda cebra por bloque de grado/sección.

    Cada cambio de (nivel, grado, sección) alterna el fondo (cebra), de modo
    que las secciones consecutivas se distingan a simple vista.
    """
    filas = []
    bloque_idx = -1
    clave_anterior = None
    numero = 0
    for est in estudiantes:
        gs = est.grado_seccion
        clave = (gs.nivel, gs.grado, gs.seccion) if gs else ("", "", "")
        titulo = f"{gs.grado} {gs.seccion}".strip() if gs else "SIN GRADO/SECCIÓN"
        if clave != clave_anterior:
            bloque_idx += 1
            clave_anterior = clave
        numero += 1
        filas.append({
            "numero": numero,
            "dni": est.numero_documento,
            "nombre": _nombre_completo(est),
            "grado_seccion": titulo,
            "zebra": bloque_idx % 2 == 0,
        })
    return filas


def padron_por_mesas(proceso, mesa_id=None, solo_sin_mesa=False):
    """Padrón de electores hábiles agrupado por mesa, para el reporte PDF.

    Retorna:
        {
            "estado": "todas" | "mesa" | "sin_mesa",
            "resumen": {"mesas": int, "habiles": int, "sin_mesa": int},
            "mesas": [
                {
                    "id": int,
                    "numero_mesa": str,
                    "descripcion": str,
                    "habiles": int,
                    "filas": [ { "numero", "dni", "nombre", "grado_seccion", "zebra" } ],
                }, ...
            ],
            "sin_mesa": [ { ... }, ... ],
        }
    """
    habiles = electores_habiles(proceso).select_related("mesa", "grado_seccion")
    total_habiles = habiles.count()
    total_sin_mesa = habiles.filter(mesa__isnull=True).count()

    resultado = {
        "estado": "sin_mesa" if solo_sin_mesa else ("mesa" if mesa_id else "todas"),
        "resumen": {"mesas": 0, "habiles": total_habiles, "sin_mesa": total_sin_mesa},
        "mesas": [],
        "sin_mesa": [],
    }

    if solo_sin_mesa:
        resultado["sin_mesa"] = _filas_padron(
            habiles.filter(mesa__isnull=True).order_by(*_ORDEN_PADRON)
        )
        return resultado

    mesas_qs = proceso.mesas.filter(es_activo=True).order_by("numero_mesa")
    if mesa_id:
        mesas_qs = mesas_qs.filter(id=mesa_id)

    resultado["resumen"]["mesas"] = len(mesas_qs) if mesa_id else mesas_qs.count()

    for mesa in mesas_qs:
        estudiantes_mesa = list(
            habiles.filter(mesa=mesa).order_by(*_ORDEN_PADRON)
        )
        resultado["mesas"].append({
            "id": mesa.id,
            "numero_mesa": mesa.numero_mesa,
            "descripcion": mesa.descripcion,
            "habiles": len(estudiantes_mesa),
            "filas": _filas_padron(estudiantes_mesa),
        })

    if not mesa_id:
        resultado["sin_mesa"] = _filas_padron(
            habiles.filter(mesa__isnull=True).order_by(*_ORDEN_PADRON)
        )

    return resultado


def filtros_padron(
    proceso,
    q="",
    mesa_id=None,
    nivel=None,
    grado=None,
    seccion=None,
    estado=None,
):
    """Queryset base de estudiantes con filtros aplicados, sin paginar.

    Reutilizable tanto para la tabla paginada como para la exportación CSV.

    Filtros:
        q        : texto libre (DNI, apellidos, nombres)
        mesa_id  : id de la mesa
        nivel    : nivel exacto ("primaria", "secundaria", ...)
        grado    : grado exacto ("1ro", "2do", ...)
        seccion  : sección exacta ("A", "B", ...)
        estado   : 'emitido' | 'pendiente' | 'ausente' | 'inhabilitado'
                   | 'sin_mesa' | None
    """
    qs = (
        proceso.estudiantes
        .select_related("mesa", "grado_seccion")
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
        if mesa_id == "sin_mesa":
            qs = qs.filter(mesa__isnull=True)
        else:
            qs = qs.filter(mesa_id=mesa_id)
    if nivel:
        qs = qs.filter(grado_seccion__nivel=nivel)
    if grado:
        qs = qs.filter(grado_seccion__grado=grado)
    if seccion:
        qs = qs.filter(grado_seccion__seccion=seccion)

    if estado == "emitido":
        qs = qs.filter(ha_votado=True)
    elif estado == "pendiente":
        qs = qs.filter(
            ha_votado=False,
            fecha_ausentismo__isnull=True,
            inhabilitado=False,
        )
    elif estado == "ausente":
        qs = qs.filter(fecha_ausentismo__isnull=False)
    elif estado == "inhabilitado":
        qs = qs.filter(inhabilitado=True)
    elif estado == "sin_mesa":
        qs = qs.filter(mesa__isnull=True)
    # estado vacío / None → "Todos": sin filtro adicional

    return qs
