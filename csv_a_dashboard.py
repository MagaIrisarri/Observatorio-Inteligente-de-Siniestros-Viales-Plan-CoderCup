"""
Convierte siniestros_rosario.csv al array `incidentes` que espera el
dashboard HTML, geocodificando las calles con Nominatim (OpenStreetMap).

Uso:
    python csv_a_dashboard.py siniestros_rosario.csv observatorio.html

Genera observatorio_con_datos.html con el array ya insertado.
"""
import csv
import io
import json
import re
import sys
import time
import urllib.parse
import urllib.request

CACHE_GEOCODING = "geocache.json"


# ---------- reparación de filas corruptas (formato viejo, por si acaso) ----------
def leer_csv_robusto(path):
    with open(path, encoding="utf-8-sig", newline="") as f:
        contenido = f.read()

    reader = csv.DictReader(io.StringIO(contenido))
    fieldnames = reader.fieldnames
    filas = list(reader)

    filas_finales = []
    reparadas = 0
    for fila in filas:
        # una fila corrupta (formato viejo) no tiene 'url' poblado:
        # todo quedó pegado en la primera columna
        if fila.get("url"):
            filas_finales.append(fila)
            continue

        primera_col = fieldnames[0]
        contenido_fila = fila.get(primera_col) or ""
        sub_reader = csv.reader(io.StringIO(contenido_fila))
        valores = next(sub_reader, [])

        if len(valores) == len(fieldnames):
            filas_finales.append(dict(zip(fieldnames, valores)))
            reparadas += 1
        else:
            # no pudimos reparar esta fila puntual: la dejamos como está
            # (probablemente se omita más adelante por falta de datos)
            filas_finales.append(fila)

    if reparadas:
        print(f"⚠️  Reparé {reparadas} fila(s) con el formato viejo (colapsadas).")

    return filas_finales


# ---------- geocoding con caché local ----------
def cargar_cache():
    try:
        with open(CACHE_GEOCODING, encoding="utf-8") as f:
            return json.load(f)
    except FileNotFoundError:
        return {}


def guardar_cache(cache):
    with open(CACHE_GEOCODING, "w", encoding="utf-8") as f:
        json.dump(cache, f, ensure_ascii=False, indent=2)


def _consultar_georef(direccion):
    """
    Consulta el endpoint /direcciones de Georef (datos.gob.ar).
    Acepta directamente el formato "Calle1 y Calle2" o "Calle1 esquina Calle2".
    """
    url = "https://apis.datos.gob.ar/georef/api/direcciones?" + urllib.parse.urlencode({
        "direccion": direccion,
        "provincia": "santa fe",
        "localidad_censal": "rosario",
        "max": 1,
    })
    req = urllib.request.Request(url, headers={"User-Agent": "observatorio-siniestros-rosario/1.0"})
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            data = json.loads(resp.read())
        direcciones = data.get("direcciones", [])
        if direcciones:
            ubicacion = direcciones[0].get("ubicacion") or {}
            lat, lon = ubicacion.get("lat"), ubicacion.get("lon")
            if lat is not None and lon is not None:
                return lat, lon
        # diagnóstico: no hubo resultado, mostramos por qué
        print(f"     (0 resultados) URL: {url}")
    except Exception as e:
        print(f"  ⚠️  Error consultando Georef '{direccion}': {e}")
    return None, None


PREFIJOS_TIPO_VIA = re.compile(
    r"^\s*(avenida|av\.?|bv\.?|boulevard|blvd\.?|avda\.?|bulevar)\s+",
    re.IGNORECASE
)


def limpiar_nombre_calle(calle):
    """
    Saca el prefijo de tipo de vía (Avenida, Bv., etc.) del nombre.
    Georef restringe la búsqueda por categoría cuando detecta esa palabra
    en la consulta, y si la calle real está categorizada distinto (ej.
    "CALLE" en vez de "AV"), la consulta no matchea nada.
    """
    return PREFIJOS_TIPO_VIA.sub("", calle).strip()


def geocodificar(calle1, calle2, cache):
    calle1, calle2 = limpiar_nombre_calle(calle1), limpiar_nombre_calle(calle2)
    if not calle1:
        return None, None  # sin calle no hay nada que buscar

    clave = f"{calle1}|{calle2}"
    if clave in cache:
        return cache[clave]

    lat = lon = None

    # intento 1: la esquina completa, formato recomendado por Georef
    if calle2:
        lat, lon = _consultar_georef(f"{calle1} y {calle2}")
        time.sleep(0.3)

    # intento 2 (fallback): solo la primera calle, aproximado
    if lat is None:
        lat, lon = _consultar_georef(calle1)
        time.sleep(0.3)

    # solo cacheamos si encontramos algo -- un fallo no debe quedar
    # guardado para siempre (podría deberse a un error transitorio,
    # o arreglarse después con un mejor query)
    if lat is not None:
        cache[clave] = [lat, lon]

    return [lat, lon]


# ---------- inferencia de tipo y clima (parche hasta que estén en el schema) ----------
def inferir_tipo(resumen, vehiculos):
    texto = f"{resumen} {vehiculos}".lower()
    if "atropell" in texto:
        return "Atropello"
    if "volc" in texto:
        return "Vuelco"
    if "moto" in texto and ("cayo" in texto or "caída" in texto or "caida" in texto):
        return "Motociclista caído"
    if re.search(r"\b(3|tres|varios)\b.*(auto|vehiculo)", texto):
        return "Colisión múltiple"
    return "Choque"


def inferir_clima(resumen):
    texto = resumen.lower()
    if "lluvia" in texto:
        return "Lluvia"
    if "niebla" in texto or "neblina" in texto:
        return "Neblina"
    if "nublad" in texto:
        return "Nublado"
    return "No registrado"


# ---------- conversión principal ----------
def convertir(path_csv):
    filas = leer_csv_robusto(path_csv)
    cache = cargar_cache()
    incidentes = []

    for fila in filas:
        if str(fila.get("es_siniestro_vial", "")).strip().lower() != "true":
            continue

        calle1 = (fila.get("ubicacion_calle1") or "").strip()
        calle2 = (fila.get("ubicacion_calle2") or "").strip()

        if not calle1:
            print(f"  -> se omite (sin calle registrada): {fila.get('url', '')}")
            continue

        print(f"Geocodificando: {calle1} y {calle2}...")
        lat, lng = geocodificar(calle1, calle2, cache)

        if lat is None:
            print(f"  -> se omite del mapa (no se pudo ubicar), pero podés revisarlo a mano")
            continue

        resumen = fila.get("resumen_breve") or ""
        vehiculos = fila.get("vehiculos_involucrados") or ""

        incidentes.append({
            "fecha": fila.get("fecha_siniestro") or "",
            "hora": fila.get("hora_aprox") or "00:00",
            "calle": f"{calle1} y {calle2}".strip(" y"),
            "lat": lat,
            "lng": lng,
            "tipo": inferir_tipo(resumen, vehiculos),
            "vehiculos": vehiculos,
            "heridos": int(float(fila.get("cantidad_heridos") or 0)),
            "fallecidos": int(float(fila.get("cantidad_fallecidos") or 0)),
            "clima": inferir_clima(resumen),
            "link": fila.get("url") or "#",
        })

    guardar_cache(cache)
    return incidentes


def inyectar_en_html(incidentes, path_html_entrada, path_html_salida):
    with open(path_html_entrada, encoding="utf-8") as f:
        html = f.read()

    js_array = "const incidentes = " + json.dumps(incidentes, ensure_ascii=False, indent=2) + ";"

    patron = re.compile(r"const incidentes = \[.*?\];", re.DOTALL)
    if not patron.search(html):
        raise RuntimeError("No encontré el array 'const incidentes = [...]' en el HTML.")

    html_nuevo = patron.sub(js_array, html, count=1)

    with open(path_html_salida, "w", encoding="utf-8") as f:
        f.write(html_nuevo)


if __name__ == "__main__":
    if len(sys.argv) != 3:
        print("Uso: python csv_a_dashboard.py siniestros_rosario.csv observatorio.html")
        sys.exit(1)

    path_csv, path_html = sys.argv[1], sys.argv[2]
    incidentes = convertir(path_csv)
    print(f"\n{len(incidentes)} siniestros geocodificados y listos.")

    salida = "observatorio_con_datos.html"
    inyectar_en_html(incidentes, path_html, salida)
    print(f"Listo: {salida}")