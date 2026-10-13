"""Comando de carga básica para demos y pruebas.

Crea:
  - 1 superusuario admin / admin
  - 1 Proceso Electoral activo
  - 2 Mesas de Votación
  - 2 Tipos de Elección (Alcalde, Regidores)
  - 4 Listas de Candidatura (2 por tipo)
  - 4 Estudiantes (2 por mesa)

Es idempotente: se puede ejecutar varias veces sin duplicar datos.
Con `--reset` primero borra los datos demo del proceso y los vuelve a crear.
"""

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand
from django.db import transaction
from django.utils import timezone

from apps.candidates.models import ListaCandidatura, TipoEleccion
from apps.voters.models import Estudiante, GradoSeccion, MesaDeVotacion, ProcesoElectoral


PROCESO_NOMBRE = "Elecciones Demo 2026"

MESAS = [
    {"numero_mesa": "Mesa 1", "descripcion": "Aula 102 - Primaria"},
    {"numero_mesa": "Mesa 2", "descripcion": "Aula 103 - Primaria"},
]

TIPOS = [
    {
        "nombre": "Alcalde",
        "orden_aparicion": 1,
        "color_fondo": "#EAF3FF",
        "listas": [
            {"nombre": "Lista A", "descripcion": "Juventud Unida"},
            {"nombre": "Lista B", "descripcion": "Renovación Escolar"},
        ],
    },
    {
        "nombre": "Regidores",
        "orden_aparicion": 2,
        "color_fondo": "#EAFBEF",
        "listas": [
            {"nombre": "Lista 1", "descripcion": "Bloque Progresista"},
            {"nombre": "Lista 2", "descripcion": "Fuerza Estudiantil"},
        ],
    },
]

# 4 votantes: 2 por mesa
ESTUDIANTES = [
    {
        "numero_documento": "42822315",
        "apellido_paterno": "AGUILAR",
        "apellido_materno": "SANDOVAL",
        "nombres": "DEMO 01",
        "nivel": "primaria",
        "grado": "1ro",
        "seccion": "A",
        "mesa": "Mesa 1",
    },
    {
        "numero_documento": "42822316",
        "apellido_paterno": "CHAPOÑAN",
        "apellido_materno": "DE LA CRUZ",
        "nombres": "DEMO 02",
        "nivel": "primaria",
        "grado": "1ro",
        "seccion": "A",
        "mesa": "Mesa 1",
    },
    {
        "numero_documento": "42822317",
        "apellido_paterno": "PEREZ",
        "apellido_materno": "GOMEZ",
        "nombres": "DEMO 03",
        "nivel": "primaria",
        "grado": "2do",
        "seccion": "B",
        "mesa": "Mesa 2",
    },
    {
        "numero_documento": "42822318",
        "apellido_paterno": "ROJAS",
        "apellido_materno": "TORRES",
        "nombres": "DEMO 04",
        "nivel": "primaria",
        "grado": "2do",
        "seccion": "B",
        "mesa": "Mesa 2",
    },
]


class Command(BaseCommand):
    help = "Carga datos demo: proceso, mesas, tipos, listas y estudiantes."

    def add_arguments(self, parser):
        parser.add_argument(
            "--reset",
            action="store_true",
            help="Borra el proceso demo (y todo en cascada) antes de recrearlo.",
        )
        parser.add_argument(
            "--admin-user",
            default="admin",
            help="Usuario del superusuario a crear (default: admin).",
        )
        parser.add_argument(
            "--admin-pass",
            default="admin",
            help="Contraseña del superusuario (default: admin).",
        )
        parser.add_argument(
            "--admin-email",
            default="admin@example.com",
            help="Email del superusuario.",
        )

    @transaction.atomic
    def handle(self, *args, **opts):
        self.stdout.write(self.style.MIGRATE_HEADING(
            "== SIVOTES · Carga de datos demo =="
        ))

        # ------------------------------------------------------------
        # 1. Superusuario
        # ------------------------------------------------------------
        User = get_user_model()
        admin_user = opts["admin_user"]

        user, created = User.objects.get_or_create(
            username=admin_user,
            defaults={
                "email": opts["admin_email"],
                "is_staff": True,
                "is_superuser": True,
                "is_active": True,
            },
        )
        # Siempre forzamos los flags por si existía como usuario común
        user.is_staff = True
        user.is_superuser = True
        user.is_active = True
        user.set_password(opts["admin_pass"])
        user.save()

        if created:
            self.stdout.write(self.style.SUCCESS(
                f"  [+] Superusuario creado: {admin_user} / {opts['admin_pass']}"
            ))
        else:
            self.stdout.write(self.style.WARNING(
                f"  [~] Superusuario existente actualizado: {admin_user}"
            ))

        # ------------------------------------------------------------
        # 2. Reset (opcional)
        # ------------------------------------------------------------
        if opts["reset"]:
            borrados = ProcesoElectoral.objects.filter(nombre=PROCESO_NOMBRE).delete()
            self.stdout.write(self.style.WARNING(
                f"  [-] Reset: {borrados[0]} objeto(s) eliminados en cascada."
            ))

        # ------------------------------------------------------------
        # 3. Proceso Electoral
        # ------------------------------------------------------------
        proceso, created = ProcesoElectoral.objects.get_or_create(
            nombre=PROCESO_NOMBRE,
            defaults={
                "activo": True,
                "cerrado": False,
                "votacion_iniciada": True,
                "fecha_inicio": timezone.now(),
                "fecha_cierre": None,
                "habilitar_voto_nulo": False,
                "habilitar_voto_invalido": False,
                "nombre_institucion": "COLEGIO NACIONAL EMBLEMÁTICO",
            },
        )
        self.stdout.write(
            f"  [+] Proceso: {proceso.nombre} (id={proceso.id})"
            if created else f"  [~] Proceso existente: {proceso.nombre} (id={proceso.id})"
        )

        # ------------------------------------------------------------
        # 4. Mesas de Votación
        # ------------------------------------------------------------
        mesas = {}
        for data in MESAS:
            mesa, _ = MesaDeVotacion.objects.get_or_create(
                proceso=proceso,
                numero_mesa=data["numero_mesa"],
                defaults={
                    "descripcion": data["descripcion"],
                    "es_activo": True,
                },
            )
            mesas[mesa.numero_mesa] = mesa
        self.stdout.write(self.style.SUCCESS(
            f"  [+] Mesas: {', '.join(mesas.keys())}"
        ))

        # ------------------------------------------------------------
        # 5. Tipos de Elección y Listas
        # ------------------------------------------------------------
        for tipo_data in TIPOS:
            tipo, _ = TipoEleccion.objects.get_or_create(
                proceso=proceso,
                nombre=tipo_data["nombre"],
                defaults={
                    "orden_aparicion": tipo_data["orden_aparicion"],
                    "es_activo": True,
                    "color_fondo": tipo_data["color_fondo"],
                },
            )

            for lista_data in tipo_data["listas"]:
                ListaCandidatura.objects.get_or_create(
                    proceso=proceso,
                    tipo_eleccion=tipo,
                    nombre=lista_data["nombre"],
                    defaults={
                        "descripcion": lista_data["descripcion"],
                        "es_activo": True,
                    },
                )

            self.stdout.write(self.style.SUCCESS(
                f"  [+] Tipo: {tipo.nombre} ({len(tipo_data['listas'])} listas)"
            ))

        # ------------------------------------------------------------
        # 6. Estudiantes
        # ------------------------------------------------------------
        grados_seccion = {}
        creados = 0
        for data in ESTUDIANTES:
            mesa = mesas.get(data["mesa"])
            gs, _ = GradoSeccion.objects.get_or_create(
                nivel=data["nivel"].strip().lower(),
                grado=data["grado"],
                seccion=data["seccion"].upper(),
                defaults={"orden": 0, "es_activo": True},
            )
            grados_seccion[(data["nivel"], data["grado"], data["seccion"])] = gs
            _, created = Estudiante.objects.get_or_create(
                numero_documento=data["numero_documento"],
                defaults={
                    "proceso": proceso,
                    "mesa": mesa,
                    "grado_seccion": gs,
                    "apellido_paterno": data["apellido_paterno"],
                    "apellido_materno": data["apellido_materno"],
                    "nombres": data["nombres"],
                    "es_activo": True,
                    "inhabilitado": False,
                    "ha_votado": False,
                },
            )
            if created:
                creados += 1

        self.stdout.write(self.style.SUCCESS(
            f"  [+] Estudiantes: {creados} nuevos / {len(ESTUDIANTES)} en total"
        ))

        # ------------------------------------------------------------
        # 7. Resumen final
        # ------------------------------------------------------------
        self.stdout.write("")
        self.stdout.write(self.style.MIGRATE_HEADING("== Resumen =="))
        self.stdout.write(f"  · Proceso        : {proceso.nombre} (id={proceso.id})")
        self.stdout.write(f"  · Mesas          : {proceso.mesas.count()}")
        self.stdout.write(f"  · Tipos elección : {proceso.tipos_eleccion.count()}")
        self.stdout.write(f"  · Listas         : {proceso.listas.count()}")
        self.stdout.write(f"  · Estudiantes    : {proceso.estudiantes.count()}")
        self.stdout.write("")
        self.stdout.write(self.style.SUCCESS("Listo. Datos demo cargados."))
        self.stdout.write("")
        self.stdout.write(self.style.HTTP_INFO("Acceso:"))
        self.stdout.write("  · Kiosco  : http://localhost:8000/")
        self.stdout.write("  · Panel   : http://localhost:8000/panel/")
        self.stdout.write("  · Admin   : http://localhost:8000/admin/")
        self.stdout.write(f"  · Usuario : {admin_user}")
        self.stdout.write(f"  · Clave   : {opts['admin_pass']}")
        self.stdout.write("")
        self.stdout.write(self.style.HTTP_INFO("DNIs para probar el kiosco:"))
        for data in ESTUDIANTES:
            self.stdout.write(
                f"  · {data['numero_documento']} — "
                f"{data['apellido_paterno']} {data['apellido_materno']}, "
                f"{data['nombres']} ({data['mesa']})"
            )
