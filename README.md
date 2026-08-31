Markdown
# 🚨 Observatorio Inteligente de Siniestros Viales (Rosario)

[![Demo en Vivo](https://img.shields.io/badge/Demo%20en%20Vivo-Vercel-black?style=for-the-badge&logo=vercel)](https://observatorio-inteligente-de-siniest.vercel.app/)
[![GitHub Repo](https://img.shields.io/badge/GitHub-Repository-blue?style=for-the-badge&logo=github)](https://github.com/MagaIrisarri/Observatorio-Inteligente-de-Siniestros-Viales-Plan-CoderCup)

Proyecto Desarrollado para el Desafío Final de CoderCup (Coderhouse)  
**Autoras:** Malena Irisarri & Magalí Irisarri  
**Año:** 2026  

---

## 📋 Descripción

El **Observatorio Inteligente de Siniestros Viales** es una solución orientada a resolver la dispersión de información sobre incidentes de tránsito en medios digitales de la ciudad de Rosario.

A través de un pipeline automatizado, el sistema rastrea noticias locales, extrae y estructura información clave mediante Modelos de Lenguaje (LLMs), enriquece las observaciones con datos meteorológicos en tiempo real y disponibiliza las métricas en un **dashboard interactivo**.

---

## 🎯 Objetivos

**Objetivo general:**  
- Automatizar la ingesta, estructuración y visualización de datos de siniestralidad vial a partir de fuentes periodísticas locales no estructuradas.

**Objetivos específicos:**  
- Implementar web scraping en diarios digitales locales (*Rosario3*, *La Capital*).  
- Procesar noticias mediante IA para extraer entidades clave (fecha, hora, ubicación, vehículos, heridos y fallecidos).  
- Enriquecer la información cruzando variables meteorológicas en tiempo real.  
- Desarrollar un dashboard interactivo georreferenciado para el análisis espacial y temporal.

---

## 🔍 El Problema vs. 🛠️ La Solución

- **El Problema:** La recopilación de datos a partir de noticias de prensa suele requerir horas de lectura manual y volcado de información en planillas, siendo un proceso lento, costoso y propenso a errores humanos.
- **La Solución:** Automatización completa mediante **Web Scraping + IA (API de Gemini) + API Meteorológica**, transformando texto no estructurado en una base de datos georreferenciada lista para el análisis estadístico.

---

## ⚙️ Metodología y Arquitectura

El pipeline de datos integra las siguientes etapas automatizadas:

```text
[ Medios de Prensa (Rosario3 / La Capital) ]
                     │
                     ▼ (Web Scraping)
     [ Extracción de Texto / Noticias ]
                     │
                     ▼ (Gemini API - Prompt Engineering)
[ JSON Estructurado: Fecha, Hora, Ubicación, Vehículos, Víctimas ]
                     │
                     ▼ (API Meteorológica)
      [ Enriquecimiento con Clima Local ]
                     │
                     ▼ (Limpieza & Deduplicación)
         [ Almacenamiento de Datos ]
                     │
                     ▼ (Dashboard / Vercel)
 [ Visualización Interactiva & Mapa Georreferenciado ]

```
**Web Scraping:** Rastreo de noticias en secciones de policiales y tránsito de medios locales de Rosario.

**Procesamiento de Lenguaje Natural (LLM):** Utilización de la API de Gemini para parsear el cuerpo de las noticias a un esquema estructurado.

**Enriquecimiento de Datos (Weather API):** Cruce espacio-temporal automático con servicios meteorológicos para incorporar las condiciones climáticas del momento del siniestro.

**Almacenamiento y Control de Duplicados:** Filtrado y validación de eventos para evitar sobreconteo por coberturas múltiples.

**Visualización y Analytics:** Dashboard web interactivo con mapas térmicos/georreferenciados y gráficos de tendencias.

## 🌐 Aplicación interactiva
Explorá los datos en tiempo real:

🔗 Observatorio Inteligente de Siniestros Viales

La app permite:

Mapa Interactivo: Visualización espacial y georreferenciada de los siniestros detectados en Rosario.

Filtros Dinámicos: Segmentación por nivel de gravedad (solo daños, heridos, fallecidos), tipo de vehículo, clima y franja horaria.

Análisis de Tendencias: Indicadores estadísticos y gráficos interactivos para la evaluación del tránsito y la accidentología.

## 🚀 Tecnologías Utilizadas
Lenguaje: Python

Extracción de Datos: Web Scraping (BeautifulSoup / Requests)

Inteligencia Artificial: Google Gemini API (google-genai)

APIs Externas: Weather API para datos climáticos históricos

Procesamiento de Datos: Pandas, NumPy

Visualización & Web: Framework de Dashboard interactivo / Plotly / Folium

Despliegue: Vercel

### 📄 Nota metodológica

Este proyecto fue desarrollado como una prueba de concepto (MVP) en el marco del concurso CoderCup de Coderhouse. Utiliza datos de fuentes periodísticas públicas y no sustituye a los registros oficiales de siniestralidad vial.

## 📬 Autoras y Contacto
Malena Irisarri — Licenciada en Estadística (Universidad Nacional de Rosario - UNR)

📧 maleirisarri@hotmail.com | 🔗 [LinkedIn](https://www.linkedin.com/in/malena-irisarri-a54766260/)

Magalí Irisarri — Estudiante de Ingeniería en Sistemas (Universidad Tecnológica Nacional - UTN)

📧 magairisarri@gmail.com | 🔗 [LinkedIn]([https://www.linkedin.com/in/malena-irisarri-a54766260/](https://www.linkedin.com/in/magali-irisarri/))
