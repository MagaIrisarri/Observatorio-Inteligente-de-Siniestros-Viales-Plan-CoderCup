from urllib.parse import urlparse

from scraper import (
    cargar_urls_procesadas,
    listar_noticias_nuevas,
    extraer_noticias,
    guardar_url_procesada,
    ANIO_MINIMO,
)
from procesador import estructurar_noticia_con_ia, guardar_resultado, es_duplicado
import agregar_clima
from csv_a_dashboard import generar_dashboard

CSV_SINIESTROS = "siniestros_rosario.csv"
HTML_TEMPLATE = "observatorio.html"

# Antes solo mirábamos la portada de cada sitio, que apenas muestra un puñado
# de noticias "destacadas" de cualquier tema, no un listado completo. Las
# secciones internas de Rosario3 (Policiales, Últimas noticias, Ciudad,
# Región) traen muchísimas más noticias por corrida. Pero lo mejor de todo es
# /tags/Siniestro-vial: es un filtro temático real del propio sitio (no un
# buscador roto) que trae casi exclusivamente noticias de siniestros viales,
# cubriendo semanas hacia atrás en una sola visita. Va primero en la lista
# porque es, por lejos, la fuente con mejor precisión.
URLS_SECCION = (
    "https://www.rosario3.com/tags/Siniestro-vial",
    "https://www.rosario3.com/seccion/policiales/",
    "https://www.lacapital.com.ar/siniestro-vial-a1006964.html",
    "https://www.lacapital.com.ar/siniestro-vial-a1006964.html/1",
    "https://www.lacapital.com.ar/siniestro-vial-a1006964.html/2",
    "https://www.lacapital.com.ar/siniestro-vial-a1006964.html/3",
    "https://www.lacapital.com.ar/secciones/policiales.html",
    "https://www.lacapital.com.ar/secciones/policiales.html/1",
    "https://www.lacapital.com.ar/secciones/policiales.html/2",
)


def main():
    print("Cargando URLs ya procesadas...")
    urls_procesadas = cargar_urls_procesadas()
    print(f"  {len(urls_procesadas)} URLs ya procesadas.")

    total_siniestros_guardados = 0

    for url_seccion in URLS_SECCION:
        print(f"\nBuscando noticias nuevas en {url_seccion}...")
        urls_nuevas = listar_noticias_nuevas(url_seccion, urls_procesadas)
        print(f"  {len(urls_nuevas)} noticias nuevas encontradas.")

        if not urls_nuevas:
            print("No hay noticias nuevas. Fin.")
            continue

        print("Extrayendo título y cuerpo de cada noticia candidata...")
        noticias = extraer_noticias(urls_nuevas)
        print(f"  {len(noticias)} noticias extraídas.")

        siniestros_guardados = 0

        for noticia in noticias:
            url = noticia["url"]
            titulo = noticia["titulo"]
            texto = noticia["texto_completo"]
            anio = noticia["anio"]
            fecha_publicacion = noticia["fecha_publicacion"]

            if anio is None or anio < ANIO_MINIMO:
                print(f"Año no válido ({anio}), se omite: {url}")
                guardar_url_procesada(url)
                urls_procesadas.add(url)
                continue

            if not texto:
                print(f"Sin texto, se omite: {url}")
                guardar_url_procesada(url)
                urls_procesadas.add(url)
                continue

            try:
                print(f"Clasificando con IA: {titulo[:60]}...")
                datos = estructurar_noticia_con_ia(titulo, texto, url, fecha_publicacion)

                ciudad = datos.get("ciudad", "").strip().lower()
                dominio = urlparse(url).netloc

                # Rosario3 es un diario pura y exclusivamente local: si no aclaró
                # ciudad (Gemini devolvió "Desconocida" o vacío), asumimos Rosario
                # en vez de descartar la noticia. En otras fuentes no vale ese
                # supuesto, porque pueden cubrir más de una ciudad.
                if dominio == "www.rosario3.com":
                    es_de_rosario = ciudad in ("", "desconocida") or "rosario" in ciudad
                else:
                    es_de_rosario = "rosario" in ciudad

                if datos.get("es_siniestro_vial") and es_de_rosario and es_duplicado(datos):
                    print("  -> Mismo siniestro ya registrado desde otra fuente, descartado")
                elif datos.get("es_siniestro_vial") and es_de_rosario:
                    guardar_resultado(datos, url)
                    siniestros_guardados += 1
                    print("  -> Es siniestro vial en Rosario, guardado en siniestros_rosario.csv")
                elif datos.get("es_siniestro_vial"):
                    print(f"  -> Es siniestro vial pero no es en Rosario (ciudad: {datos.get('ciudad')}), descartado")
                else:
                    print("  -> No es siniestro vial, descartado")

            except Exception as e:
                print(f"Error al procesar {url}: {e}")
                continue
            finally:
                # Se marca como procesada aunque no sea siniestro, para no reintentarla en la próxima corrida.
                # También se actualiza el set en memoria: si esta misma noticia aparece
                # en otra sección más adelante en esta misma corrida (es común entre
                # "Policiales" y "Últimas noticias"), no la volvemos a mandar a la IA.
                guardar_url_procesada(url)
                urls_procesadas.add(url)

        total_siniestros_guardados += siniestros_guardados
        print(f"\nListo con {url_seccion}: {siniestros_guardados} siniestros nuevos guardados.")

    if total_siniestros_guardados == 0:
        print("\nNo se guardó ningún siniestro nuevo, no hace falta actualizar la página.")
        return

    print(f"\n{total_siniestros_guardados} siniestro(s) nuevo(s) en total. Actualizando clima y la página...")
    agregar_clima.main(CSV_SINIESTROS)
    generar_dashboard(CSV_SINIESTROS, HTML_TEMPLATE)


if __name__ == "__main__":
    main()
