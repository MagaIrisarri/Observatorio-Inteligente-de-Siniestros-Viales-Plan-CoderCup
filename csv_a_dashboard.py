"""
Convierte siniestros_rosario.csv al array `incidentes` que espera el
dashboard HTML, geocodificando con la API Georef (datos.gob.ar).

Uso:
    python csv_a_dashboard.py siniestros_rosario.csv observatorio.html

Genera index.html con el array ya insertado, y sin_ubicacion_exacta.json
con los siniestros de ruta/km que no se pueden ubicar en un mapa de calles.
"""
import csv
import io
import json
import re
import sys
import time
import unicodedata
import urllib.parse
import urllib.request

# En Windows, si la salida se redirige a un pipe (ej. "| findstr"), Python
# usa cp1252 en vez de UTF-8 y los emojis de los prints (⚠️, etc.) tiran
# UnicodeEncodeError. Forzamos UTF-8 siempre para evitarlo.
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

CACHE_GEOCODING = "geocache.json"


# ---------- reparación de filas corruptas (formato viejo, por si acaso) ----------
def leer_csv_robusto(path):
    for encoding in ("utf-8-sig", "cp1252"):
        try:
            with open(path, encoding=encoding, newline="") as f:
                contenido = f.read()
            break
        except UnicodeDecodeError:
            continue

    reader = csv.reader(io.StringIO(contenido))
    fieldnames = next(reader)
    n = len(fieldnames)

    filas_finales = []
    reparadas = 0
    sin_reparar = 0

    for fila_cruda in reader:
        if not fila_cruda or all(v == "" for v in fila_cruda):
            continue  # línea vacía

        if len(fila_cruda) == n:
            filas_finales.append(dict(zip(fieldnames, fila_cruda)))
            continue

        # quedó partida en menos (o más) campos de los que debería --
        # la reconstruimos pegando de nuevo los pedazos con comas y
        # re-parseando, sin importar en cuántos fragmentos haya quedado
        reconstruida = ",".join(fila_cruda)
        valores = next(csv.reader(io.StringIO(reconstruida)), [])

        if len(valores) == n:
            filas_finales.append(dict(zip(fieldnames, valores)))
            reparadas += 1
        else:
            # no se pudo reparar -- la dejamos pasar como está (va a
            # fallar más adelante por falta de datos, pero no rompe nada)
            filas_finales.append(dict(zip(fieldnames, fila_cruda)))
            sin_reparar += 1

    if reparadas:
        print(f"⚠️  Reparé {reparadas} fila(s) con el formato viejo (colapsadas).")
    if sin_reparar:
        print(f"⚠️  {sin_reparar} fila(s) no se pudieron reparar del todo -- revisalas a mano en el CSV.")

    return filas_finales


# ---------- geocoding con caché local ----------
def cargar_cache():
    try:
        with open(CACHE_GEOCODING, encoding="utf-8") as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return {}


def guardar_cache(cache):
    with open(CACHE_GEOCODING, "w", encoding="utf-8") as f:
        json.dump(cache, f, ensure_ascii=False, indent=2)


def _consultar_georef(direccion):
    """Consulta el endpoint /direcciones de Georef (datos.gob.ar)."""
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
    Saca el prefijo de tipo de vía (Avenida, Bv., etc.). Georef restringe
    la búsqueda por categoría cuando detecta esa palabra, y si la calle
    real está categorizada distinto (ej. "CALLE" en vez de "AV"), la
    consulta no matchea nada.
    """
    return PREFIJOS_TIPO_VIA.sub("", calle or "").strip()


# Avenidas tipo autopista/circunvalación: cruzan otras calles por viaducto,
# nunca van a estar en la base de intersecciones de Georef. Se cargan a mano
# una vez confirmadas (ej. buscando la esquina en Google Maps).
# Clave: frozenset con las dos calles ya limpias (sin prefijo), en minúscula.
CORRECCIONES_INTERSECCIONES = {
    # Pellegrini y Circunvalación -- ni la avenida ni su colectora (Juan Pablo II)
    # ni el alias "Avenida Che Guevara" tienen esta intersección cargada en
    # Georef. Coordenada real, sacada de Google Maps.
    # Claves SIN tildes -- _clave_correccion saca los acentos antes de comparar.
    frozenset({"circunvalacion", "pellegrini"}): (-32.948844, -60.721929),
    # Ruta 34 y Circunvalación -- mismo problema, coordenada real de Google Maps.
    frozenset({"circunvalacion", "ruta 34"}): (-32.893655, -60.719316),
    # Doctor Vicente Medina y Circunvalación -- mismo problema.
    frozenset({"circunvalacion", "doctor vicente medina"}): (-33.00075, -60.689722),
    # Bulevar Rondeau y Vila -- Georef no la tiene cargada. Coordenada real
    # (32°53'53.5"S 60°41'29.1"W convertida a decimal).
    frozenset({"rondeau", "vila"}): (-32.898194, -60.691417),
}


def _sin_acentos(texto):
    """Saca los acentos para comparar sin importar si el texto los tiene o no."""
    normalizado = unicodedata.normalize("NFKD", texto or "")
    return "".join(c for c in normalizado if not unicodedata.combining(c))


def _clave_correccion(calle1, calle2):
    return frozenset([
        _sin_acentos(limpiar_nombre_calle(calle1)).lower(),
        _sin_acentos(limpiar_nombre_calle(calle2)).lower(),
    ])


PATRON_CIRCUNVALACION = re.compile(r"circunvalaci[oó]n", re.IGNORECASE)

# Algunas calles cambian de nombre justo en el cruce con Circunvalación --
# este alias solo se aplica cuando la otra calle del par ES Circunvalación,
# no afecta a estas calles en ninguna otra esquina.
ALIAS_JUNTO_A_CIRCUNVALACION = {
    "pellegrini": "Avenida Che Guevara",
}


def _nombre_para_geocoding(calle, es_par_con_circunvalacion=False):
    """
    Avenida de Circunvalación es una vía rápida sin esquinas reales -- Georef
    nunca la matchea en una intersección. Su colectora interna SÍ es una
    calle de superficie con cruces reales, y tiene nombre oficial propio:
    "Juan Pablo II" (Ordenanza 7851/2005). Para geocodificar sustituimos por
    ese nombre; para mostrar en el mapa seguimos usando "Circunvalación"
    (esta función solo se usa antes de consultar la API).

    Si la OTRA calle del par es Circunvalación, además revisamos si esta
    calle tiene un alias conocido (algunas cambian de nombre justo ahí).
    """
    if PATRON_CIRCUNVALACION.search(calle or ""):
        return "Juan Pablo II"
    if es_par_con_circunvalacion:
        alias = ALIAS_JUNTO_A_CIRCUNVALACION.get(_sin_acentos(limpiar_nombre_calle(calle)).lower())
        if alias:
            return alias
    return calle


def geocodificar(calle1, calle2, cache):
    """Geocodifica una intersección de dos calles. Devuelve (lat, lon, aproximado)."""
    calle1, calle2 = limpiar_nombre_calle(calle1), limpiar_nombre_calle(calle2)
    if not calle1:
        return None, None, False

    clave = f"{calle1}|{calle2}"
    if clave in cache:
        valor = cache[clave]
        if len(valor) == 2:
            valor = valor + [True]
        return valor[0], valor[1], valor[2]

    correccion = CORRECCIONES_INTERSECCIONES.get(_clave_correccion(calle1, calle2))
    if correccion:
        cache[clave] = [correccion[0], correccion[1], False]
        return correccion[0], correccion[1], False

    calle1_es_circ = bool(PATRON_CIRCUNVALACION.search(calle1))
    calle2_es_circ = bool(PATRON_CIRCUNVALACION.search(calle2))
    calle1_geo = _nombre_para_geocoding(calle1, es_par_con_circunvalacion=calle2_es_circ)
    calle2_geo = _nombre_para_geocoding(calle2, es_par_con_circunvalacion=calle1_es_circ)

    aproximado = False
    lat = lon = None

    if calle2_geo:
        lat, lon = _consultar_georef(f"{calle1_geo} y {calle2_geo}")
        time.sleep(0.3)

    if lat is None and calle2_geo:
        lat1, lon1 = _consultar_georef(calle1_geo)
        time.sleep(0.3)
        lat2, lon2 = _consultar_georef(calle2_geo)
        time.sleep(0.3)
        if lat1 is not None and lat2 is not None:
            lat, lon = (lat1 + lat2) / 2, (lon1 + lon2) / 2
            aproximado = True
        elif lat1 is not None:
            lat, lon = lat1, lon1
            aproximado = True

    if lat is None:
        lat, lon = _consultar_georef(calle1_geo)
        time.sleep(0.3)
        aproximado = True

    if lat is not None:
        cache[clave] = [lat, lon, aproximado]

    return lat, lon, aproximado


def geocodificar_altura(calle, altura, cache):
    """Geocodifica una dirección con altura (ej. "San Juan 1900")."""
    calle = limpiar_nombre_calle(calle)
    clave = f"ALTURA|{calle}|{altura}"
    if clave in cache:
        valor = cache[clave]
        return valor[0], valor[1]

    calle_geo = _nombre_para_geocoding(calle)
    lat, lon = _consultar_georef(f"{calle_geo} {altura}".strip())
    time.sleep(0.3)

    if lat is None:
        lat, lon = _consultar_georef(calle_geo)
        time.sleep(0.3)

    if lat is not None:
        cache[clave] = [lat, lon]
    return lat, lon


# ---------- filtros / detección de casos especiales ----------
PATRON_RUTA_KM = re.compile(r"\b(ruta|autopista|autov[ií]a|km|kil[oó]metro)\b", re.IGNORECASE)
VALORES_CALLE2_INVALIDOS = {"n/a", "na", "no aplica", "desconocido", "s/d", ""}


def calle2_es_valida(calle2):
    calle2 = (calle2 or "").strip()
    if calle2.lower() in VALORES_CALLE2_INVALIDOS:
        return False
    if calle2.isdigit():  # es una altura, no una calle
        return False
    return True


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
    texto = (resumen or "").lower()
    if "lluvia" in texto:
        return "Lluvia"
    if "niebla" in texto or "neblina" in texto:
        return "Neblina"
    if "nublad" in texto:
        return "Nublado"
    return "No registrado"


def clima_de_fila(fila, resumen):
    """
    Usa el clima real (columna clima_real, agregado por agregar_clima.py a
    partir de Open-Meteo) en vez de adivinarlo con palabras clave del
    resumen. Si el CSV es viejo y no tiene esa columna, o vino vacío/
    "Desconocido" para esa fecha, cae de nuevo a la inferencia por texto.
    """
    clima_real = (fila.get("clima_real") or "").strip()
    if clima_real and clima_real != "Desconocido":
        return clima_real
    return inferir_clima(resumen)


# ---------- conversión principal ----------
def convertir(path_csv):
    filas = leer_csv_robusto(path_csv)
    cache = cargar_cache()
    incidentes = []
    sin_ubicacion_exacta = []  # ruta_km y desconocida: no van al mapa, pero no se pierden
    vistos = set()  # para no duplicar el mismo siniestro contado por 2 medios

    for fila in filas:
        if str(fila.get("es_siniestro_vial", "")).strip().lower() != "true":
            print(f"  -> se omite (no es siniestro vial): {fila.get('url', '')}")
            continue

        url = fila.get("url", "")
        resumen = fila.get("resumen_breve") or ""
        vehiculos = fila.get("vehiculos_involucrados") or ""
        # si el CSV es viejo y no tiene esta columna, default a "interseccion"
        tipo_ubicacion = (fila.get("tipo_ubicacion") or "interseccion").strip().lower()
        calle1 = (fila.get("ubicacion_calle1") or "").strip()

        if not calle1:
            print(f"  -> se omite (sin calle registrada): {url}")
            continue

        # si vehiculos_involucrados tenía una coma sin comillas (típico de haber
        # abierto y vuelto a guardar el CSV en Excel), esa coma de más corre
        # todas las columnas siguientes y heridos/fallecidos dejan de ser
        # números -- se salta la fila en vez de crashear toda la corrida.
        try:
            heridos = int(float(fila.get("cantidad_heridos") or 0))
            fallecidos = int(float(fila.get("cantidad_fallecidos") or 0))
        except ValueError:
            print(f"  -> se omite (fila con columnas corridas/corruptas, revisala a mano en el CSV): {url}")
            continue

        # --- ruta/autopista con km, o ubicación que Gemini no pudo precisar ---
        if tipo_ubicacion in ("ruta_km", "desconocida"):
            ruta_nombre = (fila.get("ruta_nombre") or calle1).strip()
            print(f"  -> sin coordenada exacta ({tipo_ubicacion}): {ruta_nombre}")
            sin_ubicacion_exacta.append({
                "fecha": fila.get("fecha_siniestro") or "",
                "hora": fila.get("hora_aprox") or "00:00",
                "descripcion": ruta_nombre + (f", km {fila.get('kilometro')}" if fila.get("kilometro") else ""),
                "vehiculos": vehiculos,
                "heridos": heridos,
                "fallecidos": fallecidos,
                "link": url,
            })
            continue

        # --- calle con altura (ej. "San Juan al 1900") ---
        if tipo_ubicacion == "altura":
            altura = (fila.get("altura") or "").strip()
            clave_dup = (limpiar_nombre_calle(calle1).lower(), altura, fila.get("fecha_siniestro"))
            if clave_dup in vistos:
                print(f"  -> se omite (duplicado, ya cargado desde otra fuente): {url}")
                continue
            vistos.add(clave_dup)

            print(f"Geocodificando: {calle1} {altura}...")
            lat, lng = geocodificar_altura(calle1, altura, cache)
            if lat is None:
                print(f"  -> se omite del mapa (no se pudo ubicar), pero podés revisarlo a mano")
                continue

            incidentes.append({
                "fecha": fila.get("fecha_siniestro") or "",
                "hora": fila.get("hora_aprox") or "00:00",
                "calle": f"{calle1} al {altura}".strip(),
                "lat": lat,
                "lng": lng,
                "ubicacion_aproximada": False,
                "tipo": inferir_tipo(resumen, vehiculos),
                "vehiculos": vehiculos,
                "heridos": heridos,
                "fallecidos": fallecidos,
                "clima": clima_de_fila(fila, resumen),
                "lluvia_mm": float(fila.get("lluvia_mm") or 0.0),
                "link": url or "#",
            })
            continue

        # --- caso normal: intersección de dos calles ---
        calle2_cruda = (fila.get("ubicacion_calle2") or "").strip()

        tiene_correccion = _clave_correccion(calle1, calle2_cruda) in CORRECCIONES_INTERSECCIONES
        if not tiene_correccion and (PATRON_RUTA_KM.search(calle1) or PATRON_RUTA_KM.search(calle2_cruda)):
            print(f"  -> se omite del mapa (es ruta/km, no una esquina de ciudad): {calle1} y {calle2_cruda}")
            continue

        calle2 = calle2_cruda if calle2_es_valida(calle2_cruda) else ""

        clave_dup = (frozenset([
            limpiar_nombre_calle(calle1).lower(),
            limpiar_nombre_calle(calle2).lower(),
        ]), fila.get("fecha_siniestro"))

        if clave_dup in vistos:
            print(f"  -> se omite (duplicado, ya cargado desde otra fuente): {url}")
            continue
        vistos.add(clave_dup)

        print(f"Geocodificando: {calle1} y {calle2}...")
        lat, lng, aproximado = geocodificar(calle1, calle2, cache)

        if lat is None:
            print(f"  -> se omite del mapa (no se pudo ubicar), pero podés revisarlo a mano")
            continue

        incidentes.append({
            "fecha": fila.get("fecha_siniestro") or "",
            "hora": fila.get("hora_aprox") or "00:00",
            "calle": f"{calle1} y {calle2}".strip(" y"),
            "lat": lat,
            "lng": lng,
            "ubicacion_aproximada": aproximado,
            "tipo": inferir_tipo(resumen, vehiculos),
            "vehiculos": vehiculos,
            "heridos": heridos,
            "fallecidos": fallecidos,
            "clima": clima_de_fila(fila, resumen),
            "lluvia_mm": float(fila.get("lluvia_mm") or 0.0),
            "link": url or "#",
        })

    guardar_cache(cache)

    if sin_ubicacion_exacta:
        print(f"\n{len(sin_ubicacion_exacta)} siniestro(s) sin coordenada exacta (rutas/km) -- "
              f"quedan afuera del mapa, revisalos a mano si los querés incluir.")

    return incidentes, sin_ubicacion_exacta


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


def generar_dashboard(path_csv, path_html_entrada, path_html_salida="index.html"):
    incidentes, sin_ubicacion_exacta = convertir(path_csv)
    print(f"\n{len(incidentes)} siniestros geocodificados y listos.")

    inyectar_en_html(incidentes, path_html_entrada, path_html_salida)
    print(f"Listo: {path_html_salida}")

    if sin_ubicacion_exacta:
        with open("sin_ubicacion_exacta.json", "w", encoding="utf-8") as f:
            json.dump(sin_ubicacion_exacta, f, ensure_ascii=False, indent=2)
        print(f"Guardé {len(sin_ubicacion_exacta)} siniestro(s) sin coordenada en sin_ubicacion_exacta.json")


if __name__ == "__main__":
    if len(sys.argv) != 3:
        print("Uso: python csv_a_dashboard.py siniestros_rosario.csv observatorio.html")
        sys.exit(1)

    generar_dashboard(sys.argv[1], sys.argv[2])