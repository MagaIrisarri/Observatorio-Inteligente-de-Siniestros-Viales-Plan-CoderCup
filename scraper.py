import requests
from bs4 import BeautifulSoup
import csv
import os
import re
from urllib.parse import urljoin, urlparse


ARCHIVO_URLS_PROCESADAS = "urls_procesadas.csv"

PATRON_NOTICIA = re.compile(r"/informaciongeneral/.+-\d{8}-\d{4}\.html$")

ARCHIVO_URLS_PROCESADAS = "urls_procesadas.csv"


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
    headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"}
    response = requests.get(url_seccion, headers=headers)
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

        # Solo el dominio propio de Rosario3
        if parsed.netloc != "www.rosario3.com":
            continue

        # Los links de compartir (facebook, mail) siempre traen query string (?...)
        if parsed.query:
            continue

        # Ahora sí, chequeo el patrón SOLO contra el path, no contra la URL entera
        if PATRON_NOTICIA.search(parsed.path):
            urls_candidatas.add(href_absoluta)

    return [u for u in urls_candidatas if u not in urls_procesadas]


def extraer_noticia_rosario3(url):
    """
    Descarga el HTML de una noticia de Rosario3 y extrae título y cuerpo.
    """
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    }

    try:
        response = requests.get(url, headers=headers)
        response.raise_for_status()

        soup = BeautifulSoup(response.text, 'html.parser')

        # Extraer el título principal
        titulo_elem = soup.find('h1')
        titulo = titulo_elem.text.strip() if titulo_elem else "Sin título"

        # Extraer párrafos de texto
        cuerpo_div = soup.find('div', class_='article-body')
        if cuerpo_div:
            parrafos = cuerpo_div.find_all('p')
            texto_completo = "\n".join(
                p.get_text(strip=True) for p in parrafos if p.get_text(strip=True)
            )
        else:
            texto_completo = ""

        return {
            "url": url,
            "titulo": titulo,
            "texto_completo": texto_completo
        }

    except Exception as e:
        print(f"Error al procesar la URL: {e}")
        return None

def extraer_noticias(urls_nuevas):
    """
    Recibe una lista de URLs nuevas y devuelve una lista de dicts
    (url, titulo, texto_completo), saltando las que fallen.
    """
    noticias = []
    for url in urls_nuevas:
        try:
            noticia = extraer_noticia_rosario3(url)
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