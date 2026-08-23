"""Pruebas del dominio de solicitudes y del repositorio en memoria."""

import json
from dataclasses import FrozenInstanceError

import pytest

from mai.adaptadores.llm.falso import AdaptadorFalso
from mai.adaptadores.persistencia.repositorio_memoria import RepositorioEnMemoria
from mai.dominio.clasificacion import Clasificador
from mai.dominio.solicitudes import (
    ESTADO_INICIAL,
    LIMITE_MAXIMO,
    DatosDeSolicitudInvalidos,
    FiltrosDeListado,
    ServicioSolicitudes,
    SolicitudNoEncontrada,
)


def servicio(respuestas=None, falla=False):
    proveedor = AdaptadorFalso(respuestas, falla_siempre=falla)
    return ServicioSolicitudes(RepositorioEnMemoria(), Clasificador(proveedor))


def clasificacion(categoria="Accesos", prioridad="Alta"):
    return [json.dumps({"categoria": categoria, "prioridad": prioridad})]


DATOS = {
    "asunto": "No puedo entrar al sistema",
    "descripcion": "Me pide contraseña y la rechaza",
    "area": "Aplicaciones",
    "solicitante": "usuario001@lafortuna.com.co",
}


# ── Creación ────────────────────────────────────────────────────────────────


def test_crea_una_solicitud_con_codigo_estado_y_clasificacion():
    creada = servicio(clasificacion()).crear(**DATOS)

    assert creada.codigo == "SOL-000001"
    assert creada.estado == ESTADO_INICIAL
    assert creada.categoria == "Accesos"
    assert creada.prioridad == "Alta"
    assert creada.origen_clasificacion == "modelo"
    assert creada.confianza == "alta"


def test_los_codigos_no_se_repiten():
    servicio_ = servicio(clasificacion())

    codigos = [servicio_.crear(**DATOS).codigo for _ in range(3)]

    assert codigos == ["SOL-000001", "SOL-000002", "SOL-000003"]


def test_normaliza_el_area_contra_el_catalogo():
    creada = servicio(clasificacion()).crear(**{**DATOS, "area": "  TALENTO humano "})

    assert creada.area == "Talento Humano"


def test_usa_formulario_como_canal_por_defecto():
    assert servicio(clasificacion()).crear(**DATOS).canal == "Formulario"


def test_normaliza_el_canal_cuando_se_indica():
    creada = servicio(clasificacion()).crear(**DATOS, canal="CORREO")

    assert creada.canal == "Correo"


def test_recorta_los_espacios_del_asunto():
    creada = servicio(clasificacion()).crear(**{**DATOS, "asunto": "  Hola  "})

    assert creada.asunto == "Hola"


# ── La clasificación no puede impedir la creación ───────────────────────────


def test_la_solicitud_se_crea_aunque_el_proveedor_este_caido():
    """Dejar caer el trabajo de un usuario por un fallo nuestro seria cambiar
    un problema de calidad por uno de pérdida de datos."""
    creada = servicio(falla=True).crear(**DATOS)

    assert creada.codigo == "SOL-000001"
    assert creada.origen_clasificacion == "degradado"
    assert creada.confianza == "baja"
    assert creada.motivo_degradacion == "proveedor_no_disponible"
    assert creada.categoria == "Accesos"


def test_la_solicitud_se_crea_aunque_el_modelo_devuelva_basura():
    creada = servicio(["no soy json"]).crear(**DATOS)

    assert creada.origen_clasificacion == "degradado"
    assert creada.motivo_degradacion == "salida_no_interpretable"


def test_no_se_envia_el_solicitante_al_proveedor():
    """El dato personal se guarda en nuestro sistema pero no sale de él."""
    proveedor = AdaptadorFalso(clasificacion())
    servicio_ = ServicioSolicitudes(RepositorioEnMemoria(), Clasificador(proveedor))

    servicio_.crear(**DATOS)

    instruccion, entrada = proveedor.llamadas[0]
    assert "usuario001@lafortuna.com.co" not in instruccion + entrada


# ── Validación de entrada ───────────────────────────────────────────────────


@pytest.mark.parametrize("campo", ["asunto", "solicitante"])
def test_rechaza_un_campo_obligatorio_vacio(campo):
    with pytest.raises(DatosDeSolicitudInvalidos) as error:
        servicio(clasificacion()).crear(**{**DATOS, campo: "   "})

    assert error.value.campo == campo


def test_rechaza_un_area_desconocida():
    """Validar entrada nueva no es lo mismo que sanear el histórico: ahí un
    área vacía va a «Sin área» y el registro se conserva."""
    with pytest.raises(DatosDeSolicitudInvalidos) as error:
        servicio(clasificacion()).crear(**{**DATOS, "area": "Mercadeo"})

    assert error.value.campo == "area"


def test_rechaza_un_area_vacia():
    with pytest.raises(DatosDeSolicitudInvalidos, match="area"):
        servicio(clasificacion()).crear(**{**DATOS, "area": ""})


def test_rechaza_un_canal_desconocido():
    with pytest.raises(DatosDeSolicitudInvalidos) as error:
        servicio(clasificacion()).crear(**DATOS, canal="paloma mensajera")

    assert error.value.campo == "canal"


def test_rechaza_un_asunto_desmedido():
    """Sin cota, un cuerpo de megabytes entra a memoria y al prompt."""
    with pytest.raises(DatosDeSolicitudInvalidos, match="asunto"):
        servicio(clasificacion()).crear(**{**DATOS, "asunto": "x" * 201})


def test_acepta_una_descripcion_vacia():
    """La descripción es opcional: hay tickets que caben en el asunto."""
    creada = servicio(clasificacion()).crear(**{**DATOS, "descripcion": ""})

    assert creada.descripcion == ""


def test_no_llama_al_proveedor_si_la_validacion_falla():
    """Gastar una llamada de pago para datos que se van a rechazar es costo
    sin información."""
    proveedor = AdaptadorFalso(clasificacion())
    servicio_ = ServicioSolicitudes(RepositorioEnMemoria(), Clasificador(proveedor))

    with pytest.raises(DatosDeSolicitudInvalidos):
        servicio_.crear(**{**DATOS, "asunto": ""})

    assert proveedor.llamadas == []


# ── Consulta ────────────────────────────────────────────────────────────────


def test_consulta_una_solicitud_por_su_codigo():
    servicio_ = servicio(clasificacion())
    creada = servicio_.crear(**DATOS)

    assert servicio_.obtener(creada.codigo).asunto == creada.asunto


def test_lanza_no_encontrada_ante_un_codigo_inexistente():
    with pytest.raises(SolicitudNoEncontrada):
        servicio(clasificacion()).obtener("SOL-999999")


def test_lanza_no_encontrada_ante_un_codigo_vacio():
    with pytest.raises(SolicitudNoEncontrada):
        servicio(clasificacion()).obtener("   ")


# ── Listado y filtros ───────────────────────────────────────────────────────


def poblar(servicio_):
    servicio_.crear(**{**DATOS, "area": "Aplicaciones"})
    servicio_.crear(**{**DATOS, "area": "Calidad"})
    servicio_.crear(**{**DATOS, "area": "Aplicaciones"})


def test_lista_las_mas_recientes_primero():
    servicio_ = servicio(clasificacion())
    poblar(servicio_)

    pagina, total = servicio_.listar(FiltrosDeListado())

    assert [s.codigo for s in pagina] == ["SOL-000003", "SOL-000002", "SOL-000001"]
    assert total == 3


def test_filtra_por_area():
    servicio_ = servicio(clasificacion())
    poblar(servicio_)

    pagina, total = servicio_.listar(FiltrosDeListado(area="aplicaciones"))

    assert [s.codigo for s in pagina] == ["SOL-000003", "SOL-000001"]
    assert total == 2


def test_filtra_por_categoria_y_prioridad():
    servicio_ = servicio(clasificacion("Red", "Baja"))
    servicio_.crear(**DATOS)

    assert servicio_.listar(FiltrosDeListado(categoria="Red"))[1] == 1
    assert servicio_.listar(FiltrosDeListado(prioridad="Baja"))[1] == 1
    assert servicio_.listar(FiltrosDeListado(prioridad="Alta"))[1] == 0


def test_rechaza_un_filtro_fuera_de_catalogo():
    """Devolver [] ante «estado=cerado» haría creer que no hay tickets
    cerrados. Un valor desconocido es un error del cliente, no una búsqueda
    vacía."""
    with pytest.raises(DatosDeSolicitudInvalidos) as error:
        servicio(clasificacion()).listar(FiltrosDeListado(estado="cerado"))

    assert error.value.campo == "estado"


def test_el_total_ignora_la_paginacion():
    """Quien pagina necesita saber cuántas hay en total; devolver solo la
    página lo deja sin forma de saber si debe pedir otra."""
    servicio_ = servicio(clasificacion())
    poblar(servicio_)

    pagina, total = servicio_.listar(FiltrosDeListado(limite=2))

    assert len(pagina) == 2
    assert total == 3


def test_el_desplazamiento_avanza_la_pagina():
    servicio_ = servicio(clasificacion())
    poblar(servicio_)

    pagina, _ = servicio_.listar(FiltrosDeListado(limite=2, desplazamiento=2))

    assert [s.codigo for s in pagina] == ["SOL-000001"]


def test_el_limite_queda_acotado_por_arriba():
    """Sin cota, un cliente pide un millón y se lleva toda la memoria."""
    servicio_ = servicio(clasificacion())
    poblar(servicio_)

    pagina, _ = servicio_.listar(FiltrosDeListado(limite=10_000))

    assert len(pagina) == 3
    assert FiltrosDeListado(limite=10_000).limite > LIMITE_MAXIMO


def test_un_limite_de_cero_o_negativo_se_lleva_a_uno():
    servicio_ = servicio(clasificacion())
    poblar(servicio_)

    assert len(servicio_.listar(FiltrosDeListado(limite=0))[0]) == 1
    assert len(servicio_.listar(FiltrosDeListado(limite=-5))[0]) == 1


def test_un_desplazamiento_negativo_se_lleva_a_cero():
    servicio_ = servicio(clasificacion())
    poblar(servicio_)

    pagina, _ = servicio_.listar(FiltrosDeListado(desplazamiento=-3))

    assert len(pagina) == 3


def test_listar_sin_solicitudes_devuelve_vacio_y_no_falla():
    pagina, total = servicio(clasificacion()).listar(FiltrosDeListado())

    assert pagina == []
    assert total == 0


# ── Inmutabilidad ───────────────────────────────────────────────────────────


def test_la_solicitud_es_inmutable():
    """Un objeto mutable en un repositorio compartido permite que quien lo
    consulte lo modifique sin querer — el defecto S2 del legacy, otra vez."""
    creada = servicio(clasificacion()).crear(**DATOS)

    with pytest.raises(FrozenInstanceError):
        creada.estado = "Cerrado"  # type: ignore[misc]


def test_cambiar_el_estado_produce_una_solicitud_nueva():
    creada = servicio(clasificacion()).crear(**DATOS)

    cerrada = creada.con_estado("Cerrado")

    assert cerrada.estado == "Cerrado"
    assert creada.estado == ESTADO_INICIAL
    assert cerrada is not creada


# ── Concurrencia ────────────────────────────────────────────────────────────


def test_no_produce_codigos_duplicados_con_hilos_simultaneos():
    """Verifica que el contador entrega códigos únicos bajo acceso simultáneo.

    LO QUE ESTA PRUEBA NO ES, y conviene decirlo: no es una demostración de
    que el cerrojo haga falta hoy. Se midió el contador sin proteger bajo
    CPython 3.12 con 20 hilos y 10.000 códigos, forzando cambios de hilo con
    `setswitchinterval`, y no produjo un solo duplicado. El GIL cambia de hilo
    en fronteras de bytecode y esta secuencia es demasiado corta para que la
    carrera se manifieste. Es decir: **sin cerrojo, esta prueba también
    pasaría**.

    Entonces por qué está el cerrojo, y por qué está la prueba:

    El GIL es un detalle de implementación de CPython, no una garantía del
    lenguaje. Python 3.13 ya distribuye compilaciones sin él, y ahí una
    lectura seguida de una escritura sobre estado compartido sí se entrelaza.
    Un contador de identificadores que depende de un detalle del intérprete
    para no duplicar es una bomba con temporizador puesto en la versión
    siguiente.

    La prueba queda como red de seguridad para ese día y para cualquier
    refactor que introduzca una espera dentro de la sección crítica —eso sí
    la hace fallar de inmediato—, no como evidencia de un defecto actual.
    """
    import threading

    repositorio = RepositorioEnMemoria()
    codigos: list[str] = []
    cerrojo_de_la_prueba = threading.Lock()
    listos = threading.Barrier(20)

    def pedir_codigos():
        listos.wait()  # que los 20 arranquen a la vez, no en fila
        propios = [repositorio.siguiente_codigo() for _ in range(50)]
        with cerrojo_de_la_prueba:
            codigos.extend(propios)

    hilos = [threading.Thread(target=pedir_codigos) for _ in range(20)]
    for hilo in hilos:
        hilo.start()
    for hilo in hilos:
        hilo.join()

    assert len(codigos) == 1000
    assert len(set(codigos)) == 1000, "se repitieron códigos: el contador tiene una carrera"


def test_guardar_desde_varios_hilos_no_pierde_solicitudes():
    import threading

    repositorio = RepositorioEnMemoria()
    plantilla = servicio(clasificacion()).crear(**DATOS)
    listos = threading.Barrier(10)

    def guardar_lote():
        listos.wait()
        for _ in range(50):
            codigo = repositorio.siguiente_codigo()
            repositorio.guardar(plantilla.__class__(**{**plantilla.__dict__, "codigo": codigo}))

    hilos = [threading.Thread(target=guardar_lote) for _ in range(10)]
    for hilo in hilos:
        hilo.start()
    for hilo in hilos:
        hilo.join()

    assert repositorio.contar(FiltrosDeListado()) == 500
