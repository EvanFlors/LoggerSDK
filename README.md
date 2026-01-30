# IA FEE Backend - Intelligent Delivery Time Estimation Service

[![Python](https://img.shields.io/badge/python-3.11-blue.svg)](https://www.python.org/downloads/)
[![Flask](https://img.shields.io/badge/flask-3.1.1-green.svg)](https://flask.palletsprojects.com/)
[![Google Cloud](https://img.shields.io/badge/google--cloud-enabled-blue.svg)](https://cloud.google.com/)

Sistema inteligente de estimación de fecha de entrega (FEE) que utiliza optimización matemática y machine learning para calcular rutas óptimas de entrega considerando múltiples factores como inventario, tiempo, costo y capacidad de nodos.

## 🚀 Características Principales

- **Optimización Multiobjetivo**: Utiliza programación lineal (PuLP) para optimizar rutas considerando múltiples factores
- **Procesamiento Paralelo**: Consultas concurrentes a APIs externas para mejor rendimiento
- **Integración con BigQuery**: Conectividad con Google Cloud BigQuery para datos históricos
- **Health Checks Avanzados**: Monitoreo de conectividad y estado del servicio
- **Recálculo Dinámico**: Capacidad de recalcular rutas en caso de rechazos o cambios
- **APIs RESTful**: Endpoints bien definidos para integración

## 📋 Tabla de Contenidos

- [Instalación](#instalación)
- [Configuración](#configuración)
- [Uso](#uso)
- [API Endpoints](#api-endpoints)
- [Arquitectura](#arquitectura)
- [Desarrollo](#desarrollo)
- [Despliegue](#despliegue)
- [Monitoreo](#monitoreo)

## 🛠 Instalación

### Prerrequisitos

- Python 3.11+
- Google Cloud SDK configurado
- Acceso a BigQuery
- Docker (opcional, para contenedores)

### Instalación Local

1. **Clonar el repositorio**
   ```bash
   git clone https://github.com/Servicios-Liverpool-Infraestructura/ia_fee_back.git
   cd ia_fee_back
   ```

2. **Crear entorno virtual**
   ```bash
   python -m venv venv
   source venv/bin/activate  # En Windows: venv\Scripts\activate
   ```

3. **Instalar dependencias**
   ```bash
   pip install -r requirements.txt
   ```

4. **Configurar variables de entorno**
   ```bash
   export GOOGLE_APPLICATION_CREDENTIALS="path/to/service-account.json"
   export PORT=8080
   ```

5. **Ejecutar la aplicación**
   ```bash
   python app.py
   ```

### Instalación con Docker

```bash
# Construir imagen
docker build -t ia-fee-backend .

# Ejecutar contenedor
docker run -p 8080:8080 \
  -e GOOGLE_APPLICATION_CREDENTIALS=/app/credentials.json \
  -v /path/to/credentials.json:/app/credentials.json \
  ia-fee-backend
```

## ⚙️ Configuración

### Variables de Entorno

| Variable | Descripción | Requerido | Valor por Defecto |
|----------|-------------|-----------|-------------------|
| `PORT` | Puerto del servidor | No | `8080` |
| `GOOGLE_APPLICATION_CREDENTIALS` | Ruta a credenciales de GCP | Sí | - |

### Archivos de Configuración

El sistema requiere los siguientes archivos CSV en el directorio `DB/`:

- `CPTiempoCosto.csv`: Datos de código postal, tiempo y costo
- `NodesCapacity.csv`: Capacidad de nodos/tiendas
- `Nodes.csv`: Información de nodos

## 🔧 Uso

### Ejemplo Básico

```python
import requests

# Solicitar estimación de fecha de entrega
data = {
    "sku": "1177646331",
    "qty": 2,
    "cp": "3660",
    "weights": {
        "inventario": 0.5,
        "tiempo": 1.0,
        "costo": 2.0,
        "nodo": 0.5,
        "ruta": 0.5
    }
}

response = requests.post(
    "http://localhost:8080/fecha-estimada-entrega",
    json=data
)

print(response.json())
```

### Parámetros de Pesos

Los pesos permiten ajustar la importancia de cada factor en la optimización:

- **inventario**: Prioridad del inventario disponible (0.0 - 1.0)
- **tiempo**: Importancia del tiempo de entrega (0.0 - 3.0)
- **costo**: Peso del costo de envío (0.0 - 3.0)
- **nodo**: Importancia de la capacidad del nodo (0.0 - 1.0)
- **ruta**: Peso de la ruta específica (0.0 - 1.0)

## 📡 API Endpoints

### `POST /fecha-estimada-entrega`

Calcula la fecha estimada de entrega óptima.

**Request Body:**
```json
{
    "sku": "string",
    "qty": "integer",
    "cp": "string",
    "weights": {
        "inventario": "float",
        "tiempo": "float",
        "costo": "float",
        "nodo": "float",
        "ruta": "float"
    },
    "recalculo": "boolean (opcional)",
    "fechaCompraOriginal": "string (YYYY-MM-DD, opcional)",
    "fechaEntregaOriginal": "string (YYYY-MM-DD, opcional)",
    "tiendaRechazo": "integer (opcional)"
}
```

**Response:**
```json
{
    "inputs": {
        "sku": "1177646331",
        "qty": 2,
        "cp": "3660",
        "weights": {...}
    },
    "rutas": [
        {
            "tda_cve": 104,
            "tienda": "NOMBRE_TIENDA",
            "cantidad": 2,
            "inventario": 15,
            "tiempo": 3,
            "costo": 45.50,
            "fecha_entrega": "2025-12-05",
            "met_entrega": "Estándar"
        }
    ],
    "resumen": {
        "tiempo_procesamiento": "1250ms",
        "suma_costo_unitario": 45.50,
        "tiempo_maximo_dias": 3,
        "fecha_de_entrega": "2025-12-05",
        "cantidad_rutas_utilizadas": 1,
        "estado_modelo": "Optimal"
    }
}
```

### `GET /healthcheck`

Verificación completa del estado del servicio.

**Response:**
```json
{
    "service": "ia_fee_back",
    "status": "healthy",
    "timestamp": "2025-12-02T10:30:00Z",
    "response_time_ms": 1250.75,
    "checks": {
        "external_apis": {
            "status": "healthy",
            "details": [...]
        },
        "file_dependencies": {
            "status": "healthy",
            "details": [...]
        },
        "application": {
            "status": "healthy",
            "flask_app": "running",
            "bigquery_client": "initialized"
        }
    }
}
```

### `GET /health`

Health check básico para balanceadores de carga.

**Response:**
```json
{
    "status": "ok",
    "timestamp": "2025-12-02T10:30:00Z",
    "service": "ia_fee_back"
}
```

## 🏗 Arquitectura

### Componentes Principales

```
┌─────────────────┐    ┌─────────────────┐    ┌─────────────────┐
│   Flask API     │    │  Optimization   │    │  Data Sources   │
│                 │    │     Engine      │    │                 │
│ • REST Endpoints│───▶│ • PuLP Solver   │───▶│ • BigQuery      │
│ • Health Checks │    │ • Multi-obj.    │    │ • External APIs │
│ • Validation    │    │ • Constraints   │    │ • CSV Files     │
└─────────────────┘    └─────────────────┘    └─────────────────┘
         │                       │                       │
         ▼                       ▼                       ▼
┌─────────────────┐    ┌─────────────────┐    ┌─────────────────┐
│   Logging &     │    │   Concurrent    │    │   File System   │
│   Monitoring    │    │   Processing    │    │   & Cache       │
└─────────────────┘    └─────────────────┘    └─────────────────┘
```

### Flujo de Procesamiento

1. **Recepción de Request**: Validación de parámetros de entrada
2. **Obtención de Datos**: Consulta paralela a BigQuery y APIs externas
3. **Procesamiento**: Merge y normalización de datos
4. **Optimización**: Resolución del problema de optimización
5. **Respuesta**: Formato y entrega del resultado

### Algoritmo de Optimización

El sistema utiliza **programación lineal entera mixta** con:

- **Variables de decisión**: Cantidad a asignar por ruta
- **Variables binarias**: Selección de rutas
- **Función objetivo**: Minimización ponderada de múltiples factores
- **Restricciones**: Demanda, inventario, capacidad

## 🔧 Desarrollo

### Estructura del Proyecto

```
ia_fee_back/
├── app.py                 # Aplicación Flask principal
├── infoReal.py           # Módulo de obtención de datos
├── getNodeCapacity.py    # Utilidad para capacidad de nodos
├── getCPTiempoCosto.py   # Utilidad para datos CP
├── requirements.txt      # Dependencias Python
├── Dockerfile           # Configuración Docker
├── cloudbuild.yaml      # Configuración Google Cloud Build
├── DB/                  # Archivos de datos
│   ├── CPTiempoCosto.csv
│   ├── NodesCapacity.csv
│   └── Nodes.csv
└── README.md           # Este archivo
```

### Scripts Utilitarios

- **`getNodeCapacity.py`**: Actualiza la capacidad de nodos consultando APIs
- **`getCPTiempoCosto.py`**: Genera datos de tiempo y costo por CP

### Testing Local

```bash
# Ejecutar servidor de desarrollo
python app.py

# Probar health check
curl http://localhost:8080/health

# Probar endpoint principal
curl -X POST http://localhost:8080/fecha-estimada-entrega \
  -H "Content-Type: application/json" \
  -d '{"sku":"1177646331","qty":2,"cp":"3660","weights":{"inventario":0.5,"tiempo":1.0,"costo":2.0,"nodo":0.5,"ruta":0.5}}'
```

## 🚀 Despliegue

### Google Cloud Run

El proyecto incluye configuración para despliegue automático en Google Cloud Run:

```bash
# Desplegar usando Cloud Build
gcloud builds submit --config cloudbuild.yaml \
  --substitutions _PROJECT_ID=tu-proyecto,_SERVICE_ACCOUNT=tu-service-account
```

### Variables de Entorno en Producción

```bash
gcloud run services update cloudrun-service-fee-real \
  --set-env-vars="PORT=8080" \
  --region=us-east4
```

### Configuración de Service Account

El service account debe tener permisos para:
- BigQuery Data Viewer
- BigQuery Job User
- Cloud Run Invoker (si es privado)

## 📊 Monitoreo

### Health Checks

- **Liveness**: `GET /health` - Verifica que el servicio responda
- **Readiness**: `GET /healthcheck` - Verifica conexiones externas y dependencias

### Logs

El sistema genera logs estructurados con niveles:
- `INFO`: Operaciones normales y timing
- `ERROR`: Errores de proceso y validación

### Métricas Recomendadas

- Tiempo de respuesta por endpoint
- Tasa de éxito/fallo
- Disponibilidad de APIs externas
- Uso de recursos (CPU, memoria)

## 🐛 Troubleshooting

### Problemas Comunes

1. **Error de conexión a BigQuery**
   ```
   Solución: Verificar credenciales y permisos del service account
   ```

2. **APIs externas no responden**
   ```bash
   # Verificar conectividad
   curl http://localhost:8080/healthcheck
   ```

3. **Archivos CSV faltantes**
   ```
   Solución: Asegurar que los archivos en DB/ estén presentes
   ```

4. **Modelo no encuentra solución óptima**
   ```
   Solución: Revisar restricciones de inventario y demanda
   ```

## 📝 Contribución

1. Fork del proyecto
2. Crear rama feature (`git checkout -b feature/nueva-funcionalidad`)
3. Commit cambios (`git commit -am 'Añadir nueva funcionalidad'`)
4. Push a la rama (`git push origin feature/nueva-funcionalidad`)
5. Crear Pull Request

## 📄 Licencia

Este proyecto es propiedad de Liverpool y está sujeto a las políticas internas de la empresa.

## 🤝 Soporte

Para soporte técnico, contactar al equipo de Infraestructura Digital de Liverpool.

---

**Desarrollado con ❤️ por el equipo de Liverpool Digital Infrastructure**