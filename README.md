# Project Y4GA: AI-Powered Financial Co-pilot

Asistente financiero inteligente para análisis de operaciones Uber.

**Autor:** Ortega Mendoza Roman Yair

---

## Estructura del proyecto

```
Project_Y4GA_/
├── data_science/                          # Análisis de datos y notebooks
│   ├── Code_Complete_Extraction.ipynb     # Extracción completa de datos
│   ├── Untitled.ipynb
│   ├── YAGA_DataSet_Clean.csv
│   ├── YAGA_DataSet_Final.xlsx
│   ├── YAGA_DataSet_Operativo_Viajes_2024_2026.csv
│   ├── YAGA_DataSet_PDF_Maestro_Organizado.csv
│   ├── YAGA_Viajes_Individuales_Final.csv
│   ├── Extraction_trafic_data_Uber/       # CSVs y JSONs por mes (jun 2024 – mar 2025)
│   ├── Uber_Reports/                      # Reportes PDF semanales por mes
│   ├── Project_YAGA_R/                    # Análisis en R
│   └── Notebook Prueba/                   # Notebooks experimentales
│
├── frontend/                              # PWA dashboard de cabina
│   ├── index.html
│   └── manifest.json
│
└── yaga-backend/                          # Backend FastAPI
    ├── docker-compose.yml
    └── app/
        ├── main.py
        ├── security.py
        ├── api/v1/nlp.py
        └── services/
            ├── database.py
            ├── jornada_service.py
            └── nlp/
```
