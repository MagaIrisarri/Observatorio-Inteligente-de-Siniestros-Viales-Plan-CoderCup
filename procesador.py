import csv
import io
import json
import os
import re
import time
import pandas as pd
from pydantic import BaseModel, Field
from google import genai
from google.genai import types
from dotenv import load_dotenv
from typing import Literal, Optional

MODEL_NAME = "gemini-3.1-flash-lite"
ARCHIVO_SINIESTROS = "siniestros_rosario.csv"
MAX_REINTENTOS_IA = 3
ESPERA_BASE_SEGUNDOS = 5

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

    tipo_ubicacion: Literal["interseccion", "altura", "ruta_km", "desconocida"] = Field(
    description=(
        "Elegí 'interseccion' siempre que el texto mencione DOS calles/avenidas "
        "relacionadas con el lugar del hecho (aunque una sea 'la calle que cruzaba' "
        "o 'la calle que circulaba'), incluso si no dice explícitamente 'esquina' o 'cruce'. "
        "Usá 'altura' SOLO si el texto da un número de puerta/altura y ninguna segunda calle. "
        "Si tenés dudas entre las dos, preferí 'interseccion'."
    )
)
    ubicacion_calle1: str = Field(description="Nombre de la calle/avenida/ruta principal")
    ubicacion_calle2: Optional[str] = Field(
        default=None, description="Segunda calle SOLO si tipo_ubicacion es 'interseccion'. None en cualquier otro caso."
    )
    altura: Optional[int] = Field(
        default=None, description="Número de puerta/altura SOLO si tipo_ubicacion es 'altura'. None en cualquier otro caso."
    )
    ruta_nombre: Optional[str] = Field(
        default=None, description="Nombre de la ruta/autopista SOLO si tipo_ubicacion es 'ruta_km' (ej. 'Autopista Rosario-Santa Fe', 'RN 34'). None en cualquier otro caso."
    )
    kilometro: Optional[float] = Field(
        default=None, description="Kilómetro SOLO si tipo_ubicacion es 'ruta_km' y el texto lo menciona. None si no se menciona o no aplica."
    )

    ciudad: str = Field(default="Rosario", description="Ciudad del siniestro")
    vehiculos_involucrados: list[str] = Field(description="Lista de vehículos (ej. ['Ford EcoSport', 'Colectivo Linea K'])")
    hubo_peatones: bool = Field(description="true si hubo peatones involucrados")
    cantidad_heridos: int = Field(description="Cantidad de heridos (0 si no hay)")
    cantidad_fallecidos: int = Field(description="Cantidad de fallecidos (0 si no hay)")
    gravedad: str = Field(description="Leve, Moderado, Grave o Fatal")
    resumen_breve: str = Field(description="Resumen del hecho en máximo 20 palabras")


def _segundos_de_retry_delay(error):
    """
    Si el error trae un RetryInfo de la API (ej. 429 por rate limit), devuelve
    los segundos que Gemini pidió esperar. Si no, devuelve None.
    """
    try:
        detalles = error.details.get("error", {}).get("details", [])
        for d in detalles:
            if str(d.get("@type", "")).endswith("RetryInfo"):
                return float(d["retryDelay"].rstrip("s"))
    except (AttributeError, KeyError, ValueError, TypeError):
        pass
    return None


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
    # (no hace falta aclararlo si es obvio para su lector local). Para otras
    # fuentes no vale ese supuesto, porque pueden cubrir más de una ciudad.
    contexto_ciudad = (
        "Esta noticia proviene de Rosario3, un diario pura y exclusivamente local de "
        "la ciudad de Rosario, Santa Fe. Si el texto no menciona explícitamente que el "
        "hecho ocurrió en otra ciudad o localidad, asumí que ocurrió en Rosario."
        if "rosario3.com" in url else
        "Indicá la ciudad solo si el texto la menciona explícitamente; si no la "
        "menciona, dejá 'Desconocida'."
    )

    prompt = f"""
    Analiza la siguiente noticia de un siniestro vial y extrae la información requerida:

    {contexto_fecha}
    {contexto_ciudad}
    Título: {titulo}
    Texto: {texto}
    """

    ultimo_error = None
    for intento in range(1, MAX_REINTENTOS_IA + 1):
        try:
            response = client.models.generate_content(
                model=MODEL_NAME,
                contents=prompt,
                config=types.GenerateContentConfig(
                    response_mime_type="application/json",
                    response_schema=SiniestroVialSchema
                )
            )
            return json.loads(response.text)
        except Exception as e:
            ultimo_error = e
            if intento == MAX_REINTENTOS_IA:
                break
            espera = _segundos_de_retry_delay(e)
            if espera is None:
                espera = ESPERA_BASE_SEGUNDOS * intento  # backoff simple si no hay pista de la API
            print(f"  Error de la IA (intento {intento}/{MAX_REINTENTOS_IA}): {e}. Reintentando en {espera:.0f}s...")
            time.sleep(espera)

    raise ultimo_error


PREFIJOS_TIPO_VIA = re.compile(
    r"^\s*(avenida|av\.?|bv\.?|boulevard|blvd\.?|avda\.?|bulevar)\s+",
    re.IGNORECASE
)


def _normalizar_calle(calle):
    """
    Saca el prefijo de tipo de vía (Avenida, Bv., etc.) antes de comparar:
    Gemini a veces lo incluye ("Avenida Pellegrini") y a veces no
    ("Pellegrini") según cómo lo mencione la nota, y sin esto dos fuentes
    hablando de la misma calle no matcheaban como duplicado.
    """
    return PREFIJOS_TIPO_VIA.sub("", (calle or "").strip()).strip().lower()


def _leer_filas_robusto(path):
    """
    Igual que csv.DictReader, pero repara filas del formato viejo donde
    una fila quedó colapsada entera en la primera columna (por ejemplo,
    por un bug ya corregido en una versión anterior de guardar_resultado).
    Sin esto, es_duplicado no puede comparar contra esas filas porque
    fila.get("ubicacion_calle1") les da None.
    """
    with open(path, encoding="utf-8-sig", newline="") as f:
        reader = csv.DictReader(f)
        fieldnames = reader.fieldnames
        for fila in reader:
            if fila.get("url"):
                yield fila
                continue

            primera_col = fieldnames[0]
            sub_reader = csv.reader(io.StringIO(fila.get(primera_col) or ""))
            valores = next(sub_reader, [])
            if len(valores) == len(fieldnames):
                yield dict(zip(fieldnames, valores))
            else:
                yield fila


def es_duplicado(datos_json, path=ARCHIVO_SINIESTROS):
    """
    Compara un siniestro recién clasificado contra los ya guardados, para
    detectar el mismo hecho contado por otra fuente (Rosario3 vs La Capital,
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

    for fila in _leer_filas_robusto(path):
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

    Los siniestros en ruta/autopista con kilómetro (tipo_ubicacion == "ruta_km")
    NO se guardan: no hay forma de ubicarlos con precisión en el mapa (Georef
    no tiene puntos kilométricos), así que directamente no entran al CSV.
    Devuelve True si se guardó, False si se descartó por este motivo.
    """
    if datos_json.get("tipo_ubicacion") == "ruta_km":
        print(f"⏭️  Es siniestro vial pero en ruta/km (sin ubicación precisa), no se guarda: {url}")
        return False

    datos_para_tabla = datos_json.copy()
    datos_para_tabla["vehiculos_involucrados"] = ", ".join(datos_para_tabla["vehiculos_involucrados"])
    datos_para_tabla["url"] = url

    df = pd.DataFrame([datos_para_tabla])
    existe = os.path.exists(path)
    df.to_csv(path, mode="a", header=not existe, index=False, encoding="utf-8-sig")
    return True


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