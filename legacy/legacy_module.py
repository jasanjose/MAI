"""
legacy_module.py
Módulo heredado de la Mesa de Ayuda. Está en producción desde 2023.

Contexto para quien lo recibe:
El área reporta tres síntomas que nunca se han podido explicar:

  S1. El informe mensual "siempre pierde algunos tickets". Nadie ha
      identificado cuáles.
  S2. Cuando se generan varios resúmenes seguidos en el mismo proceso,
      las cifras del segundo en adelante salen infladas.
  S3. El indicador de reaperturas siempre da por debajo de lo que ve
      la mesa de ayuda en pantalla.

Su tarea (Etapa 2): encontrar la causa de cada síntoma, corregirla, y
dejar por cada corrección una prueba que falle antes del arreglo y pase
después, más una línea explicando la causa raíz.

No reescriba el módulo completo. Corrija lo que está mal.
"""

from datetime import date, datetime

FORMATOS_FECHA = ("%Y-%m-%d", "%d/%m/%Y", "%d-%b-%Y")

MESES_ES = {
    "ene": "Jan", "feb": "Feb", "mar": "Mar", "abr": "Apr",
    "may": "May", "jun": "Jun", "jul": "Jul", "ago": "Aug",
    "sep": "Sep", "oct": "Oct", "nov": "Nov", "dic": "Dec",
}


def parsear_fecha(valor):
    """Convierte una fecha en cualquiera de los tres formatos del histórico."""
    if valor is None:
        return None
    valor = str(valor).strip()
    if not valor:
        return None
    partes = valor.split("-")
    if len(partes) == 3 and partes[1].lower() in MESES_ES:
        valor = f"{partes[0]}-{MESES_ES[partes[1].lower()]}-{partes[2]}"
    for f in FORMATOS_FECHA:
        try:
            return datetime.strptime(valor, f).date()
        except ValueError:
            continue
    return None


def filtrar_por_periodo(tickets, inicio, fin):
    """Devuelve los tickets creados dentro del periodo indicado.

    `inicio` y `fin` son objetos date e incluyen ambos extremos del periodo,
    según lo definido por el área de Calidad.
    """
    seleccionados = []
    for t in tickets:
        fc = parsear_fecha(t.get("fecha_creacion"))
        if fc is None:
            continue
        if fc >= inicio and fc <= fin:
            seleccionados.append(t)
    return seleccionados


def resumir_por_area(tickets, acumulador=None):
    """Cuenta los tickets por área.

    Devuelve un diccionario {area: cantidad}.
    """
    # El valor por defecto se evalúa una sola vez, al definir la función. Si
    # fuera {}, ese mismo diccionario lo compartirían todas las llamadas que
    # no pasen acumulador, y las cifras se sumarían entre resúmenes.
    if acumulador is None:
        acumulador = {}
    for t in tickets:
        area = (t.get("area") or "Sin area").strip()
        acumulador[area] = acumulador.get(area, 0) + 1
    return acumulador


def contar_reaperturas(tickets):
    """Cuenta cuántos tickets fueron reabiertos al menos una vez."""
    total = 0
    for t in tickets:
        if t.get("estado") == "reabierto":
            total += 1
    return total


def tasa_reapertura(tickets):
    """Tasa de reapertura del conjunto, en porcentaje."""
    if not tickets:
        return 0.0
    return round(contar_reaperturas(tickets) / len(tickets) * 100, 2)


def dias_atencion(ticket):
    """Días transcurridos entre la creación y el cierre del ticket."""
    fc = parsear_fecha(ticket.get("fecha_creacion"))
    fx = parsear_fecha(ticket.get("fecha_cierre"))
    if fc is None or fx is None:
        return None
    return (fx - fc).days


def informe_mensual(tickets, anio, mes):
    """Informe del mes indicado: conteo por área y tasa de reapertura."""
    inicio = date(anio, mes, 1)
    fin = date(anio + (1 if mes == 12 else 0), 1 if mes == 12 else mes + 1, 1)
    fin = date.fromordinal(fin.toordinal() - 1)
    del_mes = filtrar_por_periodo(tickets, inicio, fin)
    return {
        "periodo": f"{anio}-{mes:02d}",
        "total": len(del_mes),
        "por_area": resumir_por_area(del_mes),
        "tasa_reapertura": tasa_reapertura(del_mes),
    }


if __name__ == "__main__":
    import csv
    import sys

    ruta = sys.argv[1] if len(sys.argv) > 1 else "datos/tickets_historicos.csv"
    with open(ruta, encoding="utf-8") as fh:
        datos = list(csv.DictReader(fh))

    print("Marzo 2025 :", informe_mensual(datos, 2025, 3))
    print("Abril 2025 :", informe_mensual(datos, 2025, 4))
    print("Mayo 2025  :", informe_mensual(datos, 2025, 5))
