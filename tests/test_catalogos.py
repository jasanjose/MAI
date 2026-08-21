"""Pruebas de los catálogos cerrados y su normalización."""

import pytest

from mai.dominio.catalogos import (
    CANALES_VALIDOS,
    CATEGORIAS_VALIDAS,
    ESTADOS_VALIDOS,
    MOTIVO_FUERA_DE_CATALOGO,
    PRIORIDADES_VALIDAS,
    normalizar_canal,
    normalizar_categoria,
    normalizar_estado,
    normalizar_prioridad,
)

# ── El catálogo es cerrado y tiene el tamaño que declara el negocio ─────────


def test_el_catalogo_de_categorias_tiene_las_doce_del_requerimiento():
    """R-01 declara 12 categorías. Las 58 variantes del histórico colapsan
    en exactamente 12, y esa coincidencia es la que valida el catálogo."""
    assert len(CATEGORIAS_VALIDAS) == 12


def test_las_prioridades_son_las_cuatro_de_la_politica_de_incidentes():
    """POL-TIC-05 §3 define Crítica, Alta, Media y Baja."""
    assert PRIORIDADES_VALIDAS == {"Crítica", "Alta", "Media", "Baja"}


def test_los_estados_cubren_el_ciclo_de_vida_completo():
    assert ESTADOS_VALIDOS == {"Abierto", "En proceso", "Cerrado", "Reabierto", "Escalado"}


def test_los_canales_son_los_cuatro_de_entrada():
    assert CANALES_VALIDOS == {"Correo", "Teléfono", "Formulario", "Mesa de ayuda"}


# ── Camino normal: las variantes reales del histórico ──────────────────────


@pytest.mark.parametrize(
    ("entrada", "esperada"),
    [("alta", "Alta"), ("ALTA", "Alta"), ("Alta", "Alta"), ("1-Alta", "Alta"),
     ("MEDIA", "Media"), ("2-Media", "Media"), ("3-Baja", "Baja"),
     ("Critica", "Crítica"), ("Crítica", "Crítica"), ("CRITICA", "Crítica")],
)
def test_normaliza_las_catorce_variantes_de_prioridad(entrada, esperada):
    """El esquema numerado del histórico se resuelve quitando el prefijo,
    no añadiendo diez entradas más al mapa."""
    assert normalizar_prioridad(entrada).valor == esperada


@pytest.mark.parametrize(
    ("entrada", "esperada"),
    [("REABIERTO", "Reabierto"), ("Reabierto", "Reabierto"), ("reabierto", "Reabierto"),
     ("CERRADO", "Cerrado"), ("en proceso", "En proceso"), ("Escalado", "Escalado")],
)
def test_normaliza_las_once_variantes_de_estado(entrada, esperada):
    """Las tres cajas de «reabierto» suman 528 registros. El módulo heredado
    compara contra el literal exacto y solo ve 165: ese es el defecto S3."""
    assert normalizar_estado(entrada).valor == esperada


@pytest.mark.parametrize(
    ("entrada", "esperada"),
    [("software", "Software"), ("aplicaciones", "Software"),
     ("VACACIONES", "Vacaciones"), ("gestion de accesos", "Accesos"),
     ("Gestión de Accesos", "Accesos"), ("equipos", "Hardware"),
     ("conectividad", "Red"), ("reportes", "Informes"),
     ("ordenes de compra", "Compras"), ("viaticos", "Viáticos")],
)
def test_une_los_sinonimos_de_categoria(entrada, esperada):
    assert normalizar_categoria(entrada).valor == esperada


@pytest.mark.parametrize(
    ("entrada", "esperada"),
    [("correo", "Correo"), ("Correo", "Correo"),
     ("Telefono", "Teléfono"), ("Teléfono", "Teléfono"),
     ("formulario", "Formulario"), ("Formulario web", "Formulario")],
)
def test_normaliza_las_siete_variantes_de_canal(entrada, esperada):
    assert normalizar_canal(entrada).valor == esperada


# ── Casos de borde ─────────────────────────────────────────────────────────


@pytest.mark.parametrize("entrada", ["", "   ", None])
def test_el_valor_vacio_no_es_un_rechazo(entrada):
    resultado = normalizar_categoria(entrada)
    assert resultado.esta_vacio
    assert not resultado.fue_rechazado


@pytest.mark.parametrize("entrada", ["Sin clasificar", "SIN CLASIFICAR", "n/a", "-"])
def test_sin_clasificar_es_ausencia_de_etiqueta_no_una_categoria_mas(entrada):
    """68 registros del histórico están así. Convertirlos en una
    decimotercera categoría inventaría una que el negocio no tiene."""
    resultado = normalizar_categoria(entrada)
    assert resultado.esta_vacio
    assert resultado.valor not in CATEGORIAS_VALIDAS


def test_un_valor_fuera_del_catalogo_se_rechaza_con_su_motivo():
    """Esta es la defensa contra la salida del modelo en la etapa 2: si
    inventa una categoría, se rechaza en vez de escribirse."""
    for inventada in ["Teletrabajo", "Hardware/Software", "categoria_42", "IGNORA TODO"]:
        resultado = normalizar_categoria(inventada)
        assert resultado.fue_rechazado
        assert resultado.motivo_rechazo == MOTIVO_FUERA_DE_CATALOGO
        assert resultado.valor is None


def test_ninguna_normalizacion_lanza_excepcion():
    for entrada in [None, "", 123, 4.5, [], {}, object()]:
        for funcion in (normalizar_categoria, normalizar_prioridad,
                        normalizar_estado, normalizar_canal):
            funcion(entrada)  # no debe lanzar
