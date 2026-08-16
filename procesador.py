import csv
import json
import os
import pandas as pd
from pydantic import BaseModel, Field
from google import genai
from google.genai import types
from dotenv import load_dotenv

MODEL_NAME = "gemini-3.1-flash-lite"
ARCHIVO_SINIESTROS = "siniestros_rosario.csv"

from dotenv import load_dotenv
load_dotenv()  # Carga las variables del archivo .env a os.environ

# lee el .env y carga las variables en os.environ
load_dotenv()  

client = genai.Client(api_key=os.environ["GEMINI_API_KEY"])

# 1. Definir el esquema estructurado para Pydantic
class SiniestroVialSchema(BaseModel):
    es_siniestro_vial: bool = Field(description="true si es un choque/accidente de tránsito, false si no")
    fecha_siniestro: str = Field(description="Fecha en formato YYYY-MM-DD o 'Desconocido'")
    hora_aprox: str = Field(description="Hora aproximada en formato HH:MM o 'Desconocido'")
    ubicacion_calle1: str = Field(description="Nombre de la calle/avenida principal")
    ubicacion_calle2: str = Field(description="Esquina/cruce si aplica, o 'N/A'")
    ciudad: str = Field(default="Rosario", description="Ciudad del siniestro")
    vehiculos_involucrados: list[str] = Field(description="Lista de vehículos (ej. ['Ford EcoSport', 'Colectivo Linea K'])")
    hubo_peatones: bool = Field(description="true si hubo peatones involucrados")
    cantidad_heridos: int = Field(description="Cantidad de heridos (0 si no hay)")
    cantidad_fallecidos: int = Field(description="Cantidad de fallecidos (0 si no hay)")
    gravedad: str = Field(description="Leve, Moderado, Grave o Fatal")
    resumen_breve: str = Field(description="Resumen del hecho en máximo 20 palabras")


def estructurar_noticia_con_ia(titulo, texto, url, fecha_publicacion=None):
    contexto_fecha = (
        f"Esta noticia fue publicada el {fecha_publicacion}. Usá esa fecha como referencia "
        f"para resolver expresiones relativas ('hoy', 'ayer', 'este viernes', etc.). Si el "
        f"texto no menciona explícitamente una fecha distinta para el siniestro, asumí que "
        f"ocurrió el mismo día de publicación."
        if fecha_publicacion else
        "No se pudo determinar la fecha de publicación de esta noticia."
    )
    # Rosario3 es un diario exclusivamente local de Rosario: cuando una nota de
    # ese sitio no aclara la ciudad, es porque da por sentado que es Rosario
    # (no hace falta aclararlo si es obvio para su lector local). Cadena3, en
    # cambio, cubre muchas ciudades del país, así que ahí no vale ese supuesto.
    contexto_ciudad = (
        "Esta noticia proviene de Rosario3, un diario pura y exclusivamente local de "
        "la ciudad de Rosario, Santa Fe. Si el texto no menciona explícitamente que el "
        "hecho ocurrió en otra ciudad o localidad, asumí que ocurrió en Rosario."
        if "rosario3.com" in url else
        "Esta noticia proviene de Cadena3, un medio con cobertura en varias ciudades "
        "de Argentina. Indicá la ciudad solo si el texto la menciona explícitamente; "
        "si no la menciona, dejá 'Desconocida'."
    )

    prompt = f"""
    Analiza la siguiente noticia de un siniestro vial y extrae la información requerida:

    {contexto_fecha}
    {contexto_ciudad}
    Título: {titulo}
    Texto: {texto}
    """

    response = client.models.generate_content(
        model=MODEL_NAME,
        contents=prompt,
        config=types.GenerateContentConfig(
            response_mime_type="application/json",
            response_schema=SiniestroVialSchema
        )
    )

    return json.loads(response.text)


def _normalizar_calle(calle):
    return (calle or "").strip().lower()


def es_duplicado(datos_json, path=ARCHIVO_SINIESTROS):
    """
    Compara un siniestro recién clasificado contra los ya guardados, para
    detectar el mismo hecho contado por otra fuente (Rosario3 vs Cadena3,
    URLs distintas). Se considera duplicado si comparten las mismas dos
    calles (sin importar el orden) y una fecha compatible.
    """
    if not os.path.exists(path):
        return False

    calles_nuevas = frozenset([
        _normalizar_calle(datos_json.get("ubicacion_calle1")),
        _normalizar_calle(datos_json.get("ubicacion_calle2")),
    ])
    if calles_nuevas == frozenset({""}):
        return False  # sin calles no hay con qué comparar, dejamos pasar

    fecha_nueva = datos_json.get("fecha_siniestro")

    with open(path, encoding="utf-8-sig", newline="") as f:
        for fila in csv.DictReader(f):
            calles_existentes = frozenset([
                _normalizar_calle(fila.get("ubicacion_calle1")),
                _normalizar_calle(fila.get("ubicacion_calle2")),
            ])
            if calles_existentes != calles_nuevas:
                continue

            fecha_existente = fila.get("fecha_siniestro")
            if fecha_nueva == fecha_existente or "Desconocido" in (fecha_nueva, fecha_existente):
                return True

    return False


def guardar_resultado(datos_json, url, path=ARCHIVO_SINIESTROS):
    """
    Agrega una noticia estructurada al CSV de siniestros (modo append, nunca pisa).
    Escribe el header solo si el archivo todavía no existe.
    """
    datos_para_tabla = datos_json.copy()
    datos_para_tabla["vehiculos_involucrados"] = ", ".join(datos_para_tabla["vehiculos_involucrados"])
    datos_para_tabla["url"] = url

    df = pd.DataFrame([datos_para_tabla])
    existe = os.path.exists(path)
    df.to_csv(path, mode="a", header=not existe, index=False, encoding="utf-8-sig")


if __name__ == "__main__":
    titulo_prueba = "La línea K quedó fuera de servicio tras un choque en Mendoza y Lavalle donde una mujer fue atropellada"
    texto_prueba = """
    30 de Abril de 2026. El siniestro vial ocurrió este jueves a media mañana, cuando una Ford EcoSport dobló por Mendoza y embistió a una mujer que cruzaba la calle. La víctima fue asistida por el Sies y trasladada a un centro de salud. El tránsito permanecía cortado en la zona. El servicio de la línea K quedó fuera de servicio.
    """
    url_prueba = "https://www.rosario3.com/informaciongeneral/la-linea-k-quedo-fuera-de-servicio-tras-un-choque-en-mendoza-y-lavalle-donde-una-mujer-fue-atropellada-20260430-0035.html"

    print("🤖 Enviando noticia a Gemini para estructurar...")

    try:
        datos_json = estructurar_noticia_con_ia(titulo_prueba, texto_prueba, url_prueba)

        print("\n✅ RESPUESTA ESTRUCTURADA DE LA IA:")
        print(json.dumps(datos_json, indent=4, ensure_ascii=False))

        guardar_resultado(datos_json, url_prueba)
        print("\n💾 ¡Fila agregada con éxito a 'siniestros_rosario.csv'!")

    except Exception as e:
        print(f"\n❌ Ocurrió un error: {e}")