import json
import pandas as pd
from pydantic import BaseModel, Field
from google import genai
from google.genai import types
import os
from dotenv import load_dotenv

MODEL_NAME = "gemini-flash-latest"


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


def estructurar_noticia_con_ia(titulo, texto, url):
    prompt = f"""
    Analiza la siguiente noticia de un siniestro vial y extrae la información requerida:
    
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

        datos_para_tabla = datos_json.copy()
        datos_para_tabla["vehiculos_involucrados"] = ", ".join(datos_para_tabla["vehiculos_involucrados"])
        datos_para_tabla["url"] = url_prueba

        df = pd.DataFrame([datos_para_tabla])

        print("\n📊 TABLA RESULTANTE (Pandas DataFrame):")
        print(df.to_string())

        df.to_csv("siniestros_rosario.csv", index=False, encoding="utf-8-sig")
        print("\n💾 ¡Tabla guardada con éxito en 'siniestros_rosario.csv'!")

    except Exception as e:
        print(f"\n❌ Ocurrió un error: {e}")