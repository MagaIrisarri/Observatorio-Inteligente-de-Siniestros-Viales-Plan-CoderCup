import requests
from bs4 import BeautifulSoup
import csv
import json
import os
import re
from urllib.parse import urljoin, urlparse


ARCHIVO_URLS_PROCESADAS = "urls_procesadas.csv"
ANIO_MINIMO = 2026

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
}

PALABRAS_CLAVE_TRANSITO = [
    "choque", "choco", "chocó", "chocaron", "chocar",
    "colision", "colisión", "colisiono", "colisionó",
    "accidente", "siniestro", "siniestros",
    "atropello", "atropelló", "atropellado", "atropellada",
    "volco", "volcó", "vuelco",
    "embistio", "embistió", "embestido", "embestida",
    "arrollo", "arrolló", "arrollado", "arrollada",
    "auto", "autos", "moto", "motos", "colectivo", "colectivos",
    "camion", "camión", "camiones", "bicicleta", "ciclista", "peatón",
    "peatona", "peatones", "peaton", "micro", "automovilista",
    "vehículo", "vehículos", "motociclista", "motociclistas",
]

PATRON_PALABRAS_CLAVE = re.compile(
    r"\b(" + "|".join(PALABRAS_CLAVE_TRANSITO) + r")\b",
    re.IGNORECASE
)

def filtrar_urls_por_palabra_clave(urls):
    """
    Pre-filtro barato: se queda solo con las URLs cuyo slug menciona
    algo de tránsito. No reemplaza a es_siniestro_vial (eso lo decide
    Gemini con el texto completo) — solo evita scrapear y mandar a la
    IA noticias que obviamente no son de tránsito.
    """
    return [u for u in urls if PATRON_PALABRAS_CLAVE.search(u)]


# --- Extractores específicos por sitio ---
# Cada extractor recibe (soup, url) de una noticia ya descargada y devuelve
# {"titulo", "texto_completo", "anio"}. "anio" puede dar None si no se pudo
# determinar; ANIO_MINIMO se aplica después, en extraer_noticias().

def extraer_noticia_rosario3(soup, url):
    titulo_elem = soup.find('h1')
    titulo = titulo_elem.text.strip() if titulo_elem else "Sin título"

    cuerpo_div = soup.find('div', class_='article-body')
    if cuerpo_div:
        parrafos = cuerpo_div.find_all('p')
        texto_completo = "\n".join(
            p.get_text(strip=True) for p in parrafos if p.get_text(strip=True)
        )
    else:
        texto_completo = ""

    anio = None
    fecha_publicacion = None
    match = re.search(r"-(\d{8})-\d{4}\.html$", url)
    if match:
        aaaammdd = match.group(1)
        anio = int(aaaammdd[:4])
        fecha_publicacion = f"{aaaammdd[:4]}-{aaaammdd[4:6]}-{aaaammdd[6:8]}"

    return {
        "titulo": titulo,
        "texto_completo": texto_completo,
        "anio": anio,
        "fecha_publicacion": fecha_publicacion,
    }


def extraer_noticia_cadena3(soup, url):
    titulo_elem = soup.find('h1')
    titulo = titulo_elem.text.strip() if titulo_elem else "Sin título"

    # Cadena3 no pone la fecha en la URL: viene en el JSON-LD de la nota.
    anio = None
    fecha_publicacion = None
    ld = soup.find('script', type='application/ld+json')
    if ld and ld.string:
        try:
            data = json.loads(ld.string)
            fecha = data.get('datePublished', '')
            if fecha:
                fecha_publicacion = fecha[:10]
                anio = int(fecha[:4])
        except (json.JSONDecodeError, ValueError):
            pass

    # El cuerpo vive en <article class="separador-chico">, mezclado con
    # ruido (bajadas de radio, "FOTO:", links a redes). Nos quedamos con
    # párrafos largos y descartamos el boilerplate conocido.
    texto_completo = ""
    articulo = soup.find('article', class_='separador-chico')
    if articulo:
        parrafos = []
        for p in articulo.find_all('p'):
            texto = p.get_text(strip=True)
            if len(texto) < 40 or texto.startswith("FOTO:") or "Mirá las notas de Cadena 3" in texto:
                continue
            parrafos.append(texto)
        texto_completo = "\n".join(parrafos)

    return {
        "titulo": titulo,
        "texto_completo": texto_completo,
        "anio": anio,
        "fecha_publicacion": fecha_publicacion,
    }


# --- Config por sitio: qué URLs son noticias y cómo extraerlas ---

SITIOS = {
    "www.rosario3.com": {
        "patron_url": re.compile(r"^/[^/]+/.+-\d{8}-\d{4}\.html$"),
        "extraer": extraer_noticia_rosario3,
    },
    "www.cadena3.com": {
        "patron_url": re.compile(r"^/noticia/[^/]+/[^/]+_\d+$"),
        "extraer": extraer_noticia_cadena3,
    },
}


def cargar_urls_procesadas(path=ARCHIVO_URLS_PROCESADAS):
    """
    Lee el CSV de URLs ya procesadas y devuelve un set.
    Si el archivo no existe todavía, devuelve un set vacío.
    """
    if not os.path.exists(path):
        return set()

    with open(path, "r", encoding="utf-8", newline="") as f:
        reader = csv.reader(f)
        return {fila[0] for fila in reader if fila}


def listar_noticias_nuevas(url_seccion, urls_procesadas):
    dominio = urlparse(url_seccion).netloc
    if dominio not in SITIOS:
        raise ValueError(f"Sitio no soportado: {dominio}. Agregalo a SITIOS en scraper.py.")
    patron_url = SITIOS[dominio]["patron_url"]

    response = requests.get(url_seccion, headers=HEADERS)
    response.raise_for_status()
    soup = BeautifulSoup(response.text, "html.parser")

    urls_candidatas = set()

    for link in soup.find_all("a", href=True):
        href = link["href"].strip()

        # Descartar mailto:, tel:, javascript:, anchors, etc.
        if href.startswith(("mailto:", "tel:", "javascript:", "#")):
            continue

        href_absoluta = urljoin(url_seccion, href)  # resuelve bien relativas, no concatena a mano
        parsed = urlparse(href_absoluta)

        # Solo el mismo dominio de la url_seccion que nos pasaron
        if parsed.netloc != dominio:
            continue

        # Los links de compartir (facebook, mail) siempre traen query string (?...)
        if parsed.query:
            continue

        # Chequeo el patrón de noticia propio de este sitio, SOLO contra el path
        if not patron_url.search(parsed.path):
            continue

        urls_candidatas.add(href_absoluta)

    return [u for u in urls_candidatas if u not in urls_procesadas]


def extraer_noticia(url):
    """
    Descarga el HTML de una noticia y la delega al extractor del sitio
    que corresponda según el dominio de la URL.
    """
    dominio = urlparse(url).netloc
    if dominio not in SITIOS:
        print(f"Sitio no soportado: {dominio}")
        return None

    try:
        response = requests.get(url, headers=HEADERS)
        response.raise_for_status()

        soup = BeautifulSoup(response.text, 'html.parser')
        datos = SITIOS[dominio]["extraer"](soup, url)

        return {"url": url, **datos}

    except Exception as e:
        print(f"Error al procesar la URL: {e}")
        return None


def extraer_noticias(urls_nuevas):
    """
    Recibe una lista de URLs nuevas y devuelve una lista de dicts
    (url, titulo, texto_completo, anio), saltando las que fallen.
    No filtra por año: eso lo decide quien llame, para poder marcar
    las descartadas como procesadas (ver ANIO_MINIMO).
    """
    noticias = []
    for url in urls_nuevas:
        try:
            noticia = extraer_noticia(url)
            if noticia:
                noticias.append(noticia)
        except Exception as e:
            print(f"Error extrayendo {url}: {e}")
            continue
    return noticias


def guardar_url_procesada(url, path=ARCHIVO_URLS_PROCESADAS):
    """
    Agrega una URL al CSV de procesadas (modo append, nunca pisa).
    """
    existe = os.path.exists(path)
    with open(path, "a", encoding="utf-8", newline="") as f:
        writer = csv.writer(f)
        if not existe:
            writer.writerow(["url"])
        writer.writerow([url])


# --- PRUEBA CON TU NOTICIA DE LA LÍNEA K ---
if __name__ == "__main__":
    urls_prueba = [
        "https://www.rosario3.com/informaciongeneral/la-linea-k-quedo-fuera-de-servicio-tras-un-choque-en-mendoza-y-lavalle-donde-una-mujer-fue-atropellada-20260430-0035.html"
    ]

    for url in urls_prueba:
        print("\nProcesando noticia de Rosario3...")
        urls_procesadas = cargar_urls_procesadas()
        urls_nuevas = listar_noticias_nuevas(url, urls_procesadas)
        noticias = extraer_noticias(urls_nuevas)

        for noticia in noticias:
            if noticia:
                print("\n" + "="*50)
                print(f"✅ TÍTULO EXTRAÍDO:\n{noticia['titulo']}")
                print("="*50)
                print(f"\n📄 TEXTO EXTRAÍDO (Primeros 400 caracteres):\n{noticia['texto_completo'][:400]}...\n")
                print("="*50)
                guardar_url_procesada(noticia["url"])
