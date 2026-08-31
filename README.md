# 🚨 Observatorio Inteligente de Siniestros Viales (Rosario)

[![App de visualización](https://img.shields.io/badge/Demo%20en%20Vivo-Vercel-black?style=for-the-badge&logo=vercel)](https://observatorio-inteligente-de-siniest.vercel.app/)
[![GitHub Repo](https://img.shields.io/badge/GitHub-Repository-blue?style=for-the-badge&logo=github)](https://github.com/MagaIrisarri/Observatorio-Inteligente-de-Siniestros-Viales-Plan-CoderCup)

> **Proyecto Desarrollado para el Desafío Final de CoderCup (Coderhouse)**  

---

## 📌 Visión General

El **Observatorio Inteligente de Siniestros Viales** es una solución orientada a resolver la dispersión de información sobre incidentes de tránsito en medios digitales. 

A través de un pipeline automatizado, el sistema rastrea noticias locales, extrae y estructura información clave mediante Modelos de Lenguaje (LLMs), enriquece las observaciones con datos meteorológicos en tiempo real y disponibiliza las métricas en un **dashboard interactivo**.

---

## 🔍 El Problema vs. 🛠️ La Solución

* **El Problema:** La recopilación de datos a partir de noticias de prensa suele requerir horas de lectura manual y volcado de información en planillas, siendo un proceso lento, costoso y propenso a errores humanos.
* **La Solución:** Automatización completa mediante **Web Scraping + IA (API de Gemini) + API Meteorológica**, transformando texto no estructurado en una base de datos georreferenciada lista para el análisis estadístico.

---

## 🏗️ Arquitectura del Pipeline de Datos

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

📊 Características del Dashboard
Mapa Interactivo: Visualización espacial y georreferenciada de los siniestros detectados en la ciudad de Rosario.

Filtros Dinámicos: Segmentación por nivel de gravedad (solo daños, heridos, fallecidos), tipo de vehículo, clima y franja horaria.

Análisis de Tendencias: Indicadores estadísticos y gráficos interactivos para la evaluación del tránsito y la accidentología.

🚀 Tecnologías Utilizadas
Lenguaje: Python

Extracción de Datos: Web Scraping (BeautifulSoup / Requests)

Inteligencia Artificial: Google Gemini API (google-genai)

APIs Externas: Weather API para datos climáticos históricos

Procesamiento de Datos: Pandas, NumPy

Visualización & Web: Framework de Dashboard interactivo / Plotly / Folium

Despliegue: Vercel

🌐 Demo en Vivo y Repositorio
Aplicación Web: Ver Dashboard Funcionando

Código Fuente: GitHub Repository

👩‍💻 Autoras
Malena Irisarri — Licenciada en Estadística (Universidad Nacional de Rosario - UNR)

Magalí Irisarri — Estudiante de Ingeniería en Sistemas de Información (Universidad Tecnológica Nacional - UTN)

Nota: Este proyecto fue desarrollado como una prueba de concepto (MVP) en el marco del concurso CoderCup de Coderhouse. Utiliza datos de fuentes periodísticas públicas y no sustituye a los registros oficiales de siniestralidad vial.
