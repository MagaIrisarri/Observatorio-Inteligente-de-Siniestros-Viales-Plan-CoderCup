from urllib.parse import urlparse

from scraper import (
    cargar_urls_procesadas,
    listar_noticias_nuevas,
    extraer_noticias,
    guardar_url_procesada,
    filtrar_urls_por_palabra_clave,
    ANIO_MINIMO,
)
from procesador import estructurar_noticia_con_ia, guardar_resultado, es_duplicado

URLS_SECCION = (
    "https://www.rosario3.com/seccion/policiales/",
    "https://www.rosario3.com/seccion/informacion-general/",
    "https://www.rosario3.com/seccion/ultimas-noticias/",
    "https://www.rosario3.com/seccion/ciudad/",
    "https://www.rosario3.com/seccion/region/",
    "https://www.cadena3.com/rosario",
)

def main():
    print("Cargando URLs ya procesadas...")
    urls_procesadas = cargar_urls_procesadas()
    print(f"  {len(urls_procesadas)} URLs ya procesadas.")

    for url_seccion in URLS_SECCION:
        print(f"\nBuscando noticias nuevas en {url_seccion}...")
        urls_nuevas = listar_noticias_nuevas(url_seccion, urls_procesadas)
        print(f"  {len(urls_nuevas)} noticias nuevas encontradas.")

        if not urls_nuevas:
            print("No hay noticias nuevas. Fin.")
            continue

        urls_candidatas = filtrar_urls_por_palabra_clave(urls_nuevas)
        print(f"  {len(urls_candidatas)} candidatas tras el filtro de palabras clave.")

        # Las descartadas por el filtro no se scrapean, pero se marcan como procesadas
        # para no volver a evaluarlas en la próxima corrida.
        for url in set(urls_nuevas) - set(urls_candidatas):
            guardar_url_procesada(url)
            urls_procesadas.add(url)

        if not urls_candidatas:
            print("Ninguna URL nueva pasó el filtro. Fin.")
            continue

        print("Extrayendo título y cuerpo de cada noticia candidata...")
        noticias = extraer_noticias(urls_candidatas)
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
                # en vez de descartar la noticia. En Cadena3 no vale ese supuesto,
                # porque cubre muchas ciudades distintas.
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
                guardar_url_procesada(url)
                urls_procesadas.add(url)

        print(f"\nListo con {url_seccion}: {siniestros_guardados} siniestros nuevos guardados.")


if __name__ == "__main__":
    main()
