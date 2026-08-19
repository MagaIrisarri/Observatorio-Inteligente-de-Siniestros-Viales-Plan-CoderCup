"""
Agrega clima histórico real a siniestros_rosario.csv, usando la fecha de
cada siniestro y la API gratuita de Open-Meteo (sin API key).

Uso:
    python agregar_clima.py siniestros_rosario.csv

Agrega (o actualiza, si ya existían) dos columnas al mismo archivo:
    - clima_real: categoría derivada del código WMO (Despejado, Nublado,
      Niebla, Lluvia, Tormenta, etc.)
    - lluvia_mm: milímetros de lluvia ese día en Rosario (0.0 si no llovió)
"""
import csv
import io
import json
import sys
import urllib.parse
import urllib.request

# Coordenadas de Rosario, Santa Fe
LAT_ROSARIO = -32.9468
LON_ROSARIO = -60.6393

# Traducción de código WMO a una categoría simple y legible
CODIGO_WMO_A_CATEGORIA = {
    0: "Despejado",
    1: "Mayormente despejado",
    2: "Parcialmente nublado",
    3: "Nublado",
    45: "Niebla",
    48: "Niebla",
    51: "Llovizna",
    53: "Llovizna",
    55: "Llovizna",
    56: "Llovizna helada",
    57: "Llovizna helada",
    61: "Lluvia",
    63: "Lluvia",
    65: "Lluvia intensa",
    66: "Lluvia helada",
    67: "Lluvia helada",
    71: "Nieve",
    73: "Nieve",
    75: "Nieve intensa",
    77: "Nieve (granizo fino)",
    80: "Chubascos",
    81: "Chubascos",
    82: "Chubascos intensos",
    85: "Chubascos de nieve",
    86: "Chubascos de nieve intensos",
    95: "Tormenta",
    96: "Tormenta con granizo",
    99: "Tormenta con granizo intenso",
}


def leer_csv_robusto(path):
    """Igual criterio que en csv_a_dashboard.py: repara filas colapsadas."""
    with open(path, encoding="utf-8-sig", newline="") as f:
        contenido = f.read()

    reader = csv.reader(io.StringIO(contenido))
    fieldnames = next(reader)
    n = len(fieldnames)

    filas = []
    for fila_cruda in reader:
        if not fila_cruda or all(v == "" for v in fila_cruda):
            continue
        if len(fila_cruda) == n:
            filas.append(dict(zip(fieldnames, fila_cruda)))
            continue
        reconstruida = ",".join(fila_cruda)
        valores = next(csv.reader(io.StringIO(reconstruida)), [])
        if len(valores) == n:
            filas.append(dict(zip(fieldnames, valores)))
        else:
            filas.append(dict(zip(fieldnames, fila_cruda)))

    return filas, fieldnames


def obtener_clima_historico(fecha_min, fecha_max):
    """
    Una sola consulta a Open-Meteo para todo el rango de fechas.
    Devuelve un dict {fecha (YYYY-MM-DD): (categoria, lluvia_mm)}.
    """
    url = "https://archive-api.open-meteo.com/v1/archive?" + urllib.parse.urlencode({
        "latitude": LAT_ROSARIO,
        "longitude": LON_ROSARIO,
        "start_date": fecha_min,
        "end_date": fecha_max,
        "daily": "weather_code,precipitation_sum",
        "timezone": "America/Argentina/Buenos_Aires",
    })
    print(f"Consultando clima histórico de Rosario ({fecha_min} a {fecha_max})...")
    req = urllib.request.Request(url, headers={"User-Agent": "observatorio-siniestros-rosario/1.0"})
    with urllib.request.urlopen(req, timeout=30) as resp:
        data = json.loads(resp.read())

    fechas = data["daily"]["time"]
    codigos = data["daily"]["weather_code"]
    lluvias = data["daily"]["precipitation_sum"]

    resultado = {}
    for fecha, codigo, lluvia in zip(fechas, codigos, lluvias):
        categoria = CODIGO_WMO_A_CATEGORIA.get(codigo, f"Código {codigo}")
        resultado[fecha] = (categoria, lluvia or 0.0)
    return resultado


def main(path_csv):
    filas, fieldnames = leer_csv_robusto(path_csv)

    fechas_validas = sorted({
        f["fecha_siniestro"] for f in filas
        if f.get("fecha_siniestro") and f["fecha_siniestro"] != "Desconocido"
    })
    if not fechas_validas:
        print("No encontré fechas válidas en el CSV, no hay nada para consultar.")
        return

    clima_por_fecha = obtener_clima_historico(fechas_validas[0], fechas_validas[-1])

    for fila in filas:
        fecha = fila.get("fecha_siniestro")
        if fecha in clima_por_fecha:
            categoria, lluvia_mm = clima_por_fecha[fecha]
        else:
            categoria, lluvia_mm = "Desconocido", ""
        fila["clima_real"] = categoria
        fila["lluvia_mm"] = lluvia_mm

    nuevos_fieldnames = list(fieldnames)
    for campo in ("clima_real", "lluvia_mm"):
        if campo not in nuevos_fieldnames:
            nuevos_fieldnames.append(campo)

    with open(path_csv, "w", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=nuevos_fieldnames)
        writer.writeheader()
        writer.writerows(filas)

    con_lluvia = sum(1 for f in filas if isinstance(f["lluvia_mm"], (int, float)) and f["lluvia_mm"] and f["lluvia_mm"] > 0)
    print(f"\nListo: {path_csv} actualizado con clima.")
    print(f"{len(filas)} filas procesadas, {con_lluvia} con lluvia registrada ese día.")


if __name__ == "__main__":
    if len(sys.argv) != 2:
        print("Uso: python agregar_clima.py siniestros_rosario.csv")
        sys.exit(1)
    main(sys.argv[1])
