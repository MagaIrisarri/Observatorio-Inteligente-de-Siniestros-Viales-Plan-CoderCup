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


MESES_ES = {
    "enero": 1, "febrero": 2, "marzo": 3, "abril": 4, "mayo": 5, "junio": 6,
    "julio": 7, "agosto": 8, "septiembre": 9, "setiembre": 9, "octubre": 10,
    "noviembre": 11, "diciembre": 12,
}


def extraer_noticia_lacapital(soup, url):
    titulo_elem = soup.find('h1', class_='nota-title')
    titulo = titulo_elem.get_text(strip=True) if titulo_elem else "Sin título"

    # El cuerpo viene partido en varios div.article-body, intercalados con
    # banners e imágenes -> hay que unir los <p> de todos, no solo del
    # primero. El bloque de "Noticias relacionadas" también usa esta clase
    # pero no tiene <p> adentro (usa <h3>), así que no hace falta excluirlo.
    parrafos = []
    for bloque in soup.find_all('div', class_='article-body'):
        for p in bloque.find_all('p'):
            texto = p.get_text(strip=True)
            if texto and not texto.startswith(">>"):  # "Leer más" internos
                parrafos.append(texto)
    texto_completo = "\n".join(parrafos)

    # A diferencia de Rosario3, acá la fecha real viene directo en el HTML
    # (span.nota-fecha, ej. "7 de agosto 2026"), no hay que inferirla del texto.
    anio = None
    fecha_publicacion = None
    fecha_tag = soup.find('span', class_='nota-fecha')
    if fecha_tag:
        match = re.search(
            r"(\d{1,2})\s+de\s+(\w+)\s+(?:de\s+)?(\d{4})",
            fecha_tag.get_text(strip=True),
            re.IGNORECASE,
        )
        if match:
            dia, mes_nombre, anio_str = match.groups()
            mes = MESES_ES.get(mes_nombre.lower())
            if mes:
                anio = int(anio_str)
                fecha_publicacion = f"{anio_str}-{mes:02d}-{int(dia):02d}"

    return {
        "titulo": titulo,
        "texto_completo": texto_completo,
        "anio": anio,
        "fecha_publicacion": fecha_publicacion,
    }


# --- Config por sitio: qué URLs son noticias y cómo extraerlas ---

PATRON_LACAPITAL = re.compile(r"-n\d+\.html$")

SITIOS = {
    "www.rosario3.com": {
        "patron_url": re.compile(r"^/[^/]+/.+-\d{8}-\d{4}\.html$"),
        "extraer": extraer_noticia_rosario3,
    },
    "www.lacapital.com.ar": {
        "patron_url": PATRON_LACAPITAL,
        "extraer": extraer_noticia_lacapital,
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
