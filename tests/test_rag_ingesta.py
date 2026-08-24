"""Pruebas de la ingesta de políticas.

El corpus real no se versiona, así que estas pruebas usan
`tests/fixtures/politica_de_prueba.pdf`: 970 bytes escritos a mano en
sintaxis PDF, con la misma forma que los documentos reales —cabecera con
código y versión, secciones numeradas, subsecciones con viñeta y una sección
sin cuerpo—. Es mejor ingeniería que versionar el material entregado y hace
que CI corra sin él.
"""

from pathlib import Path

import pytest

from mai.dominio.politicas import Fragmento
from mai.rag.ingesta import (
    LARGO_MINIMO_FRAGMENTO,
    ErrorDeIngesta,
    extraer_texto,
    fragmentar,
    ingerir,
    leer_cabecera,
)

FIXTURE = Path(__file__).parent / "fixtures" / "politica_de_prueba.pdf"


def texto_de_ejemplo() -> str:
    return (
        "Política de Vacaciones\n"
        "LA FORTUNA S.A. · Código POL-GTH-01 · Versión 3 · Vigente desde el 1 de febrero\n"
        "1. Objeto y alcance\n"
        "Regular la solicitud y el disfrute de las vacaciones.\n"
        "2. Causación\n"
        "Cada colaborador causa quince (15) días hábiles por año.\n"
        "3. Solicitud y aprobación\n"
        " 3.1. La solicitud debe radicarse con quince (15) días de anticipación.\n"
        " 3.2. La aprobación corresponde al jefe inmediato.\n"
    )


# ── Extracción ──────────────────────────────────────────────────────────────


def test_extrae_el_texto_de_un_pdf():
    texto = extraer_texto(FIXTURE)

    assert "POL-TST-99" in texto
    assert "cinco (5) dias habiles" in texto


def test_normaliza_el_caracter_de_control_de_la_vineta():
    """ReportLab representa la viñeta con \\x7f (DEL). Sin normalizarlo,
    ninguna expresión regular encuentra las subsecciones: medido, 0 de 43."""
    texto = extraer_texto(FIXTURE)

    assert "\x7f" not in texto


def test_conserva_los_saltos_de_linea_que_separan_secciones():
    """Es lo único que la fragmentación necesita del PDF."""
    assert extraer_texto(FIXTURE).count("\n") > 3


def test_un_archivo_que_no_es_pdf_lanza_un_error_del_dominio(tmp_path):
    """Nunca una excepción cruda de la librería hacia arriba."""
    falso = tmp_path / "no_soy_pdf.pdf"
    falso.write_text("esto es texto plano", encoding="utf-8")

    with pytest.raises(ErrorDeIngesta, match="no_soy_pdf"):
        extraer_texto(falso)


def test_un_archivo_inexistente_lanza_un_error_del_dominio(tmp_path):
    with pytest.raises(ErrorDeIngesta):
        extraer_texto(tmp_path / "no_existe.pdf")


# ── Cabecera ────────────────────────────────────────────────────────────────


def test_lee_el_codigo_la_version_y_el_titulo_de_la_cabecera():
    codigo, titulo, version = leer_cabecera(texto_de_ejemplo(), "respaldo")

    assert codigo == "POL-GTH-01"
    assert titulo == "Política de Vacaciones"
    assert version == "3"


def test_prefiere_el_codigo_del_contenido_al_nombre_del_archivo():
    """Si alguien renombra el PDF, las citas ya emitidas siguen apuntando al
    código correcto."""
    codigo, _, _ = leer_cabecera(texto_de_ejemplo(), "nombre-de-archivo-distinto")

    assert codigo == "POL-GTH-01"


def test_usa_el_nombre_del_archivo_si_la_cabecera_no_trae_codigo():
    """Un documento sin código se ingiere igual: perderlo sería peor."""
    codigo, _, version = leer_cabecera("1. Objeto\nTexto.\n", "POL-XXX-01")

    assert codigo == "POL-XXX-01"
    assert version == "sin versión"


def test_no_falla_con_un_texto_vacio():
    codigo, titulo, _ = leer_cabecera("", "respaldo")

    assert codigo == "respaldo"
    assert titulo == "respaldo"


# ── Fragmentación ───────────────────────────────────────────────────────────


def fragmentos_de_ejemplo() -> list[Fragmento]:
    return fragmentar(texto_de_ejemplo(), "POL-GTH-01", "Política de Vacaciones", "3")


def test_produce_un_fragmento_por_seccion_numerada():
    secciones = [f.seccion for f in fragmentos_de_ejemplo()]

    assert secciones == ["1", "2", "3", "3.1", "3.2"]


def test_la_cita_sale_de_la_estructura_del_documento():
    """`POL-GTH-01 §3.1` es verificable: quien la lea puede abrir el PDF en
    esa sección. Con ventanas fijas habría que inventar identificadores que no
    significan nada para una persona."""
    fragmento = next(f for f in fragmentos_de_ejemplo() if f.seccion == "3.1")

    assert fragmento.cita == "POL-GTH-01 §3.1"


def test_el_texto_anterior_a_la_seccion_uno_no_produce_fragmento():
    """La cabecera es metadato, no contenido consultable."""
    textos = " ".join(f.texto for f in fragmentos_de_ejemplo())

    assert "LA FORTUNA" not in textos


def test_una_subseccion_hereda_el_titulo_de_su_seccion():
    """«Solicitud y aprobación» no aparece en el texto de §3.1, pero es la
    palabra que alguien escribiría al preguntar."""
    fragmento = next(f for f in fragmentos_de_ejemplo() if f.seccion == "3.1")

    assert fragmento.titulo_padre == "Solicitud y aprobación"
    assert "Solicitud y aprobación" in fragmento.texto_para_buscar


def test_los_titulos_no_se_duplican_en_el_texto_indexado():
    """Repetirlos inflaría su frecuencia y haría que una sección pareciera más
    relevante de lo que es solo por llamarse como la pregunta."""
    fragmento = next(f for f in fragmentos_de_ejemplo() if f.seccion == "1")

    assert fragmento.texto_para_buscar.count("Objeto y alcance") == 1


def test_una_seccion_sin_cuerpo_propio_queda_con_texto_vacio():
    """Su contenido vive en las subsecciones; su título sobrevive como padre."""
    fragmento = next(f for f in fragmentos_de_ejemplo() if f.seccion == "3")

    assert fragmento.texto == ""
    assert fragmento.titulo_seccion == "Solicitud y aprobación"


def test_no_confunde_una_cifra_de_tabla_con_una_seccion():
    """«1 al 20 de enero» y «15. » no son secciones. El título de una sección
    empieza con letra."""
    texto = "1. Objeto\nCuerpo.\n1 al 20 de enero y 1 al 15 de julio\n15. \n"

    assert [f.seccion for f in fragmentar(texto, "X", "T", "1")] == ["1"]


def test_un_texto_sin_secciones_no_produce_fragmentos():
    assert fragmentar("Solo prosa, sin numerar.\n", "X", "T", "1") == []


def test_un_texto_vacio_no_produce_fragmentos():
    assert fragmentar("", "X", "T", "1") == []


def test_colapsa_los_espacios_sobrantes_del_cuerpo():
    texto = "1. Objeto\nUna   linea    con     espacios.\n"

    assert fragmentar(texto, "X", "T", "1")[0].texto == "Una linea con espacios."


# ── Ingesta completa ────────────────────────────────────────────────────────


def test_ingiere_una_carpeta_y_reporta_lo_que_hizo(tmp_path):
    import shutil

    shutil.copy(FIXTURE, tmp_path / "politica.pdf")

    fragmentos, reporte = ingerir(tmp_path)

    assert reporte.documentos_leidos == 1
    assert reporte.fragmentos == len(fragmentos)
    assert reporte.documentos_ilegibles == []
    assert all(len(f.texto) >= LARGO_MINIMO_FRAGMENTO for f in fragmentos)


def test_descarta_los_fragmentos_sin_cuerpo_y_los_cuenta(tmp_path):
    """Nada desaparece en silencio: el descarte va al reporte."""
    import shutil

    shutil.copy(FIXTURE, tmp_path / "politica.pdf")

    _, reporte = ingerir(tmp_path)

    assert reporte.descartados_por_cortos > 0


def test_un_documento_ilegible_no_detiene_a_los_demas(tmp_path):
    """Quedarse sin cuatro políticas porque una falló sería peor que responder
    con cuatro y declarar que falta una."""
    import shutil

    shutil.copy(FIXTURE, tmp_path / "buena.pdf")
    (tmp_path / "rota.pdf").write_text("no soy un pdf", encoding="utf-8")

    fragmentos, reporte = ingerir(tmp_path)

    assert reporte.documentos_leidos == 1
    assert len(reporte.documentos_ilegibles) == 1
    assert "rota.pdf" in reporte.documentos_ilegibles[0]
    assert fragmentos


def test_una_carpeta_sin_pdf_devuelve_vacio_y_no_falla(tmp_path):
    """Cero documentos es un resultado válido y visible, no un error."""
    fragmentos, reporte = ingerir(tmp_path)

    assert fragmentos == []
    assert reporte.documentos_leidos == 0
    assert reporte.fragmentos == 0
