Y4GA_Project: Is AI-powered financial copilot designed for digital platform drivers

🤖 Project Y4GA: AI-Powered Financial Co-pilot

¡Bienvenido a **Project Y4GA**! Este repositorio contiene el Motor de Extracción (ETL) principal para mi asistente financiero inteligente. 

El objetivo de este proyecto es automatizar la lectura, limpieza y estructuración de mis reportes de ganancias semanales de Uber, transformando archivos PDF desordenados en un **DataSet** limpio y listo para ser analizado mediante bases de datos y comandos de voz.

---

## 🛠️ Tecnologías y Herramientas

* **Python 3:** El lenguaje principal del motor.
* **pdfplumber:** Biblioteca especializada para la extracción de texto en crudo desde los recibos PDF.
* **Regex (Expresiones Regulares):** Lógica avanzada (`re`) para buscar y extraer con precisión montos, nombres y fechas, ignorando el ruido visual del documento.

---

## 🚀 Arquitectura del Proyecto

Este repositorio cuenta con dos versiones del código para distintos propósitos:

1. **`First_notebook.ipynb` (Entorno de Desarrollo):** Una Jupyter Notebook con propósitos pedagógicos. Contiene Markdowns, explicaciones detalladas y comentarios sobre cómo funcionan las Expresiones Regulares utilizadas. Ideal para aprender el *por qué* detrás del código.
   
2. **`First_codigo_uber.ipynb` (Entorno de Producción):** El script consolidado y optimizado. Realiza el proceso de extracción de principio a fin en una sola ejecución, listo para alimentar la base de datos de **YAGA**.

---

## 📊 Ejemplo de Salida (Output)

El script toma un PDF de 24 páginas y genera un resumen financiero instantáneo y estructurado:

👤 CONDUCTOR:          Roman Yair Ortega
📅 SEMANA:             Del 15/12/2025 al 22/12/2025
🚗 VIAJES:             67
--------------------------------------------------
💰 DESGLOSE:
   (+) Monto Bruto:    $8,246.63
   (+) Propinas:       $45.00
   (+) Incentivos:     $1,100.00
   (-) Impuestos:      -$1,099.30
==================================================

---
*Este proyecto es la Fase 1 del ecosistema Y4GA.*