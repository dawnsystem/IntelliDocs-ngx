# AI Scanner - Guía de Instalación y Configuración

Esta guía proporciona instrucciones completas para la instalación, configuración y puesta en marcha del sistema AI Scanner en IntelliDocs.

## Tabla de Contenidos

- [Requisitos Previos](#requisitos-previos)
- [Instalación](#instalacion)
- [Configuración Básica](#configuracion-basica)
- [Configuración Avanzada](#configuracion-avanzada)
- [Training de Modelos Custom](#training-modelos-custom)
- [Verificación de Instalación](#verificacion)

---

## Requisitos Previos {#requisitos-previos}

### Hardware

#### Requisitos Mínimos
- **CPU**: 4 cores
- **RAM**: 8 GB
- **Almacenamiento**: 10 GB libres (para modelos ML)
- **Red**: Conexión a Internet para descarga inicial de modelos

#### Requisitos Recomendados
- **CPU**: 8+ cores
- **RAM**: 16+ GB
- **Almacenamiento**: 20+ GB libres
- **GPU**: NVIDIA GPU con CUDA 11.x+ (opcional, mejora rendimiento 10-20x)

### Software

#### Requisitos Base
- Python 3.11+
- Docker 24.0+ y Docker Compose 2.0+ (para instalación Docker)
- PostgreSQL 15+ o SQLite (base de datos)
- Redis 7.0+ (para caché y task queue)

#### Dependencias Python
Las siguientes dependencias se instalan automáticamente:
```
torch>=2.0.0
transformers>=4.30.0
spacy>=3.5.0
opencv-python>=4.8.0
pytesseract>=0.3.10
scikit-learn>=1.3.0
```

---

## Instalación {#instalacion}

### Opción 1: Instalación con Docker (Recomendada)

El método Docker es el más simple y garantiza que todas las dependencias estén correctamente configuradas.

#### 1. Descargar Configuración

```bash
# Clonar el repositorio
git clone https://github.com/dawnsystem/IntelliDocs-ngx.git
cd IntelliDocs-ngx

# O descargar el archivo docker-compose
wget https://raw.githubusercontent.com/dawnsystem/IntelliDocs-ngx/main/docker/compose/docker-compose.intellidocs.yml
```

#### 2. Configurar Variables de Entorno

Crea un archivo `.env` o `docker-compose.env` con las siguientes variables:

```bash
# ====================================
# CONFIGURACIÓN AI SCANNER
# ====================================

# Habilitar AI Scanner (requerido)
PAPERLESS_ENABLE_AI_SCANNER=true

# Habilitar funciones ML (BERT, NER, búsqueda semántica)
PAPERLESS_ENABLE_ML_FEATURES=true

# Habilitar OCR avanzado (tablas, escritura a mano, formularios)
PAPERLESS_ENABLE_ADVANCED_OCR=true

# ====================================
# MODELOS ML
# ====================================

# Modelo de clasificación (opciones: distilbert-base-uncased, bert-base-multilingual-cased)
PAPERLESS_ML_CLASSIFIER_MODEL=distilbert-base-uncased

# Modelo NER de spaCy (opciones: en_core_web_sm, en_core_web_lg, es_core_news_sm, es_core_news_lg)
PAPERLESS_NER_MODEL=en_core_web_sm

# ====================================
# UMBRALES DE CONFIANZA
# ====================================

# Umbral para aplicación automática (0.0-1.0, recomendado: 0.80)
PAPERLESS_AI_AUTO_APPLY_THRESHOLD=0.80

# Umbral para sugerencias (0.0-1.0, recomendado: 0.60)
PAPERLESS_AI_SUGGEST_THRESHOLD=0.60

# ====================================
# OPTIMIZACIÓN
# ====================================

# Usar GPU (requiere nvidia-docker)
PAPERLESS_USE_GPU=false

# Caché de modelos ML
PAPERLESS_ML_MODEL_CACHE=/usr/src/paperless/ml_cache

# Número de workers para procesamiento
PAPERLESS_TASK_WORKERS=2

# ====================================
# TESSERACT OCR
# ====================================

# Idiomas OCR (separados por +)
PAPERLESS_OCR_LANGUAGE=eng+spa

# Motor OCR (opciones: tesseract, easyocr)
PAPERLESS_OCR_MODE=skip_noarchive
```

#### 3. Iniciar el Sistema

```bash
# Usando docker-compose
docker compose -f docker/compose/docker-compose.intellidocs.yml up -d

# O con el script de instalación
bash -c "$(curl -sL https://raw.githubusercontent.com/dawnsystem/IntelliDocs-ngx/main/install-paperless-ngx.sh)"
```

#### 4. Verificar el Despliegue

```bash
# Ver logs
docker compose -f docker/compose/docker-compose.intellidocs.yml logs -f webserver

# Verificar estado de contenedores
docker compose -f docker/compose/docker-compose.intellidocs.yml ps

# Verificar health checks
docker inspect intellidocs-webserver --format='{{.State.Health.Status}}'
```

### Opción 2: Instalación Bare Metal

Para instalaciones sin Docker, sigue estos pasos:

#### 1. Instalar Dependencias del Sistema

**Ubuntu/Debian:**
```bash
sudo apt-get update
sudo apt-get install -y \
    python3.11 python3.11-dev python3-pip \
    tesseract-ocr tesseract-ocr-eng tesseract-ocr-spa \
    libpq-dev postgresql redis-server \
    libmagic-dev libzbar0 poppler-utils \
    libxml2 libxslt1-dev libatlas-base-dev \
    libjpeg-dev zlib1g-dev libwebp-dev
```

**macOS:**
```bash
brew install python@3.11 tesseract tesseract-lang \
    postgresql redis libmagic zbar poppler \
    libxml2 libxslt openblas
```

#### 2. Clonar y Configurar el Proyecto

```bash
# Clonar repositorio
git clone https://github.com/dawnsystem/IntelliDocs-ngx.git
cd IntelliDocs-ngx

# Crear entorno virtual
python3.11 -m venv venv
source venv/bin/activate

# Instalar dependencias
pip install -U pip wheel
pip install -r requirements.txt
```

#### 3. Descargar Modelos ML

```bash
# Modelo de spaCy para NER
python -m spacy download en_core_web_sm
# O para español
python -m spacy download es_core_news_sm

# Los modelos BERT se descargan automáticamente al primer uso
# (requiere ~500MB de espacio)
```

#### 4. Configurar Base de Datos

**PostgreSQL:**
```bash
# Crear base de datos
sudo -u postgres createdb paperless
sudo -u postgres createuser paperless -P

# Configurar en paperless.conf
PAPERLESS_DBENGINE=postgresql
PAPERLESS_DBHOST=localhost
PAPERLESS_DBNAME=paperless
PAPERLESS_DBUSER=paperless
PAPERLESS_DBPASS=tu_password
```

**SQLite (solo para pruebas):**
```bash
# SQLite es la opción por defecto
PAPERLESS_DBENGINE=sqlite
```

#### 5. Configurar AI Scanner

Crea o edita `paperless.conf`:

```bash
# Copiar archivo de ejemplo
cp paperless.conf.example paperless.conf

# Añadir configuración AI Scanner
cat >> paperless.conf << 'EOF'

# AI Scanner Configuration
PAPERLESS_ENABLE_AI_SCANNER=true
PAPERLESS_ENABLE_ML_FEATURES=true
PAPERLESS_ENABLE_ADVANCED_OCR=true
PAPERLESS_ML_CLASSIFIER_MODEL=distilbert-base-uncased
PAPERLESS_AI_AUTO_APPLY_THRESHOLD=0.80
PAPERLESS_AI_SUGGEST_THRESHOLD=0.60
PAPERLESS_USE_GPU=false
PAPERLESS_ML_MODEL_CACHE=/var/lib/paperless/ml_cache
EOF
```

#### 6. Inicializar y Ejecutar

```bash
# Aplicar migraciones
python manage.py migrate

# Crear superusuario
python manage.py createsuperuser

# Recopilar archivos estáticos
python manage.py collectstatic --no-input

# Iniciar servicios

# Terminal 1: Redis
redis-server

# Terminal 2: Webserver
python manage.py runserver

# Terminal 3: Task worker
celery -A paperless worker -l INFO

# Terminal 4: Consumer (opcional)
python manage.py document_consumer
```

---

## Configuración Básica {#configuracion-basica}

### Habilitar/Deshabilitar Funciones

Puedes controlar qué funciones del AI Scanner están activas:

```bash
# Deshabilitar completamente el AI Scanner
PAPERLESS_ENABLE_AI_SCANNER=false

# Deshabilitar solo funciones ML avanzadas
PAPERLESS_ENABLE_ML_FEATURES=false

# Deshabilitar solo OCR avanzado
PAPERLESS_ENABLE_ADVANCED_OCR=false
```

### Configurar Umbrales de Confianza

Los umbrales determinan qué tan segura debe estar la IA para aplicar cambios:

```bash
# Auto-aplicar solo sugerencias muy confiables (≥90%)
PAPERLESS_AI_AUTO_APPLY_THRESHOLD=0.90

# Sugerir para revisión con confianza media-alta (≥70%)
PAPERLESS_AI_SUGGEST_THRESHOLD=0.70
```

**Recomendaciones por caso de uso:**

| Caso de Uso | Auto-Apply | Suggest | Notas |
|-------------|-----------|---------|-------|
| Conservador | 0.90 | 0.75 | Máxima precisión, mínima automatización |
| Balanceado | 0.80 | 0.60 | **Configuración por defecto** |
| Agresivo | 0.70 | 0.50 | Máxima automatización, puede requerir más correcciones |
| Solo sugerencias | 1.00 | 0.50 | Nunca aplica automáticamente |

### Seleccionar Modelos ML

#### Modelos de Clasificación (BERT)

```bash
# Modelos pequeños (rápidos, menos precisos)
PAPERLESS_ML_CLASSIFIER_MODEL=distilbert-base-uncased  # 66M parámetros, ~250MB

# Modelos medianos (balanceados)
PAPERLESS_ML_CLASSIFIER_MODEL=bert-base-uncased  # 110M parámetros, ~420MB
PAPERLESS_ML_CLASSIFIER_MODEL=bert-base-multilingual-cased  # 110M parámetros, ~420MB

# Modelos grandes (lentos, muy precisos)
PAPERLESS_ML_CLASSIFIER_MODEL=bert-large-uncased  # 340M parámetros, ~1.3GB
```

#### Modelos NER (spaCy)

```bash
# Inglés
PAPERLESS_NER_MODEL=en_core_web_sm  # 12MB, básico
PAPERLESS_NER_MODEL=en_core_web_md  # 40MB, mejorado
PAPERLESS_NER_MODEL=en_core_web_lg  # 560MB, mejor precisión

# Español
PAPERLESS_NER_MODEL=es_core_news_sm  # 12MB, básico
PAPERLESS_NER_MODEL=es_core_news_md  # 40MB, mejorado
PAPERLESS_NER_MODEL=es_core_news_lg  # 560MB, mejor precisión

# Multiidioma
PAPERLESS_NER_MODEL=xx_ent_wiki_sm  # 12MB, multiidioma básico
```

**Instalación de modelos adicionales:**
```bash
# Docker
docker exec -it intellidocs-webserver python -m spacy download es_core_news_lg

# Bare metal
source venv/bin/activate
python -m spacy download es_core_news_lg
```

---

## Configuración Avanzada {#configuracion-avanzada}

### Configuración GPU

Para acelerar el procesamiento ML 10-20x con GPU NVIDIA:

#### Docker con GPU

1. **Instalar NVIDIA Container Toolkit:**
```bash
# Ubuntu/Debian
distribution=$(. /etc/os-release;echo $ID$VERSION_ID)
curl -s -L https://nvidia.github.io/nvidia-docker/gpgkey | sudo apt-key add -
curl -s -L https://nvidia.github.io/nvidia-docker/$distribution/nvidia-docker.list | \
    sudo tee /etc/apt/sources.list.d/nvidia-docker.list
sudo apt-get update && sudo apt-get install -y nvidia-container-toolkit
sudo systemctl restart docker
```

2. **Configurar docker-compose.yml:**
```yaml
services:
  webserver:
    deploy:
      resources:
        reservations:
          devices:
            - driver: nvidia
              count: 1
              capabilities: [gpu]
    environment:
      - PAPERLESS_USE_GPU=true
```

3. **Reiniciar el stack:**
```bash
docker compose down
docker compose up -d
```

#### Bare Metal con GPU

```bash
# Instalar CUDA Toolkit
wget https://developer.download.nvidia.com/compute/cuda/repos/ubuntu2204/x86_64/cuda-keyring_1.0-1_all.deb
sudo dpkg -i cuda-keyring_1.0-1_all.deb
sudo apt-get update
sudo apt-get install -y cuda-11-8

# Instalar PyTorch con CUDA
pip install torch torchvision torchaudio --index-url https://download.pytorch.org/whl/cu118

# Habilitar GPU en configuración
echo "PAPERLESS_USE_GPU=true" >> paperless.conf
```

**Verificar GPU:**
```bash
# Docker
docker exec intellidocs-webserver python -c "import torch; print(f'CUDA available: {torch.cuda.is_available()}')"

# Bare metal
python -c "import torch; print(f'CUDA available: {torch.cuda.is_available()}')"
```

### Configuración de Caché ML

El sistema cachea modelos ML para mejorar rendimiento:

```bash
# Ubicación del caché (debe ser persistente)
PAPERLESS_ML_MODEL_CACHE=/var/lib/paperless/ml_cache

# En Docker, asegurar volumen persistente
volumes:
  - ml_cache:/usr/src/paperless/ml_cache
```

**Limpiar caché:**
```bash
# Docker
docker exec intellidocs-webserver rm -rf /usr/src/paperless/ml_cache/*

# Bare metal
rm -rf /var/lib/paperless/ml_cache/*
```

### Configuración de Workers

Ajustar el número de workers según recursos disponibles:

```bash
# Número de workers Celery
PAPERLESS_TASK_WORKERS=2  # Para 4 GB RAM
PAPERLESS_TASK_WORKERS=4  # Para 8 GB RAM
PAPERLESS_TASK_WORKERS=8  # Para 16+ GB RAM

# Concurrencia de workers
CELERY_WORKER_CONCURRENCY=2
```

### Configuración de OCR Avanzado

```bash
# Habilitar extracción de tablas
PAPERLESS_ENABLE_TABLE_EXTRACTION=true

# Habilitar reconocimiento de escritura a mano
PAPERLESS_ENABLE_HANDWRITING_RECOGNITION=true

# Habilitar detección de formularios
PAPERLESS_ENABLE_FORM_DETECTION=true

# Motor de OCR
PAPERLESS_OCR_ENGINE=tesseract  # o 'easyocr'

# Idiomas para Tesseract
PAPERLESS_OCR_LANGUAGE=eng+spa+fra+deu

# Idiomas para EasyOCR (si se usa)
PAPERLESS_EASYOCR_LANGUAGES=en,es,fr,de
```

**Instalar idiomas adicionales de Tesseract:**
```bash
# Docker
docker exec intellidocs-webserver apt-get update && \
docker exec intellidocs-webserver apt-get install -y \
    tesseract-ocr-fra tesseract-ocr-deu

# Ubuntu/Debian
sudo apt-get install -y \
    tesseract-ocr-fra tesseract-ocr-deu tesseract-ocr-ita
```

---

## Training de Modelos Custom {#training-modelos-custom}

El AI Scanner puede entrenarse con tus propios documentos para mejorar la precisión.

### Clasificador de Tipos de Documento

#### 1. Preparar Datos de Training

Exporta documentos ya clasificados:

```bash
# Docker
docker exec intellidocs-webserver python manage.py export_training_data \
    --output /tmp/training_data.json \
    --min-docs-per-type 10

# Bare metal
python manage.py export_training_data \
    --output /tmp/training_data.json \
    --min-docs-per-type 10
```

Formato del archivo JSON:
```json
[
  {
    "document_id": 123,
    "title": "Factura - Acme Corp - 2024-01-15",
    "content": "FACTURA\nAcme Corporation...",
    "document_type": "Factura",
    "correspondent": "Acme Corp",
    "tags": ["fiscal", "2024"]
  }
]
```

#### 2. Entrenar el Modelo

```bash
# Docker
docker exec intellidocs-webserver python manage.py train_classifier \
    --input /tmp/training_data.json \
    --model-output /usr/src/paperless/ml_cache/custom_classifier \
    --epochs 3 \
    --batch-size 16

# Bare metal
python manage.py train_classifier \
    --input /tmp/training_data.json \
    --model-output /var/lib/paperless/ml_cache/custom_classifier \
    --epochs 3 \
    --batch-size 16
```

**Parámetros de training:**
- `--epochs`: Número de pasadas sobre los datos (recomendado: 3-5)
- `--batch-size`: Documentos por batch (ajustar según RAM: 8-32)
- `--learning-rate`: Tasa de aprendizaje (default: 2e-5)
- `--validation-split`: Porcentaje para validación (default: 0.2)

#### 3. Usar el Modelo Custom

```bash
# Actualizar configuración
PAPERLESS_ML_CLASSIFIER_MODEL=/usr/src/paperless/ml_cache/custom_classifier

# Reiniciar servicios
docker compose restart webserver
```

### Entrenar Modelo NER Custom

Para extraer entidades específicas de tu dominio:

#### 1. Preparar Datos Anotados

Formato de anotación (JSON):
```json
{
  "documents": [
    {
      "text": "El contrato 2024-ABC fue firmado por Juan Pérez.",
      "entities": [
        {"start": 12, "end": 20, "label": "CONTRACT_ID"},
        {"start": 36, "end": 46, "label": "PERSON"}
      ]
    }
  ]
}
```

#### 2. Entrenar con spaCy

```bash
# Convertir a formato spaCy
python manage.py convert_ner_training_data \
    --input annotations.json \
    --output training_data.spacy

# Entrenar modelo
python -m spacy train \
    es_core_news_sm \
    --output ./custom_ner \
    --training training_data.spacy \
    --dev training_data.spacy \
    --n-iter 30
```

#### 3. Usar Modelo Custom

```bash
PAPERLESS_NER_MODEL=/path/to/custom_ner
```

### Fine-tuning de Umbrales

Ajustar umbrales basándose en métricas reales:

#### 1. Analizar Precisión Actual

```bash
# Generar reporte de precisión
docker exec intellidocs-webserver python manage.py analyze_ai_accuracy \
    --days 30 \
    --output /tmp/accuracy_report.json
```

Salida de ejemplo:
```json
{
  "auto_applied": {
    "total": 450,
    "correct": 423,
    "accuracy": 0.94
  },
  "suggested": {
    "total": 180,
    "accepted": 145,
    "rejected": 35,
    "acceptance_rate": 0.81
  },
  "recommendations": {
    "auto_apply_threshold": 0.85,
    "suggest_threshold": 0.65
  }
}
```

#### 2. Ajustar Umbrales

Basándote en el reporte:
```bash
# Si accuracy > 95%, puedes ser más agresivo
PAPERLESS_AI_AUTO_APPLY_THRESHOLD=0.75

# Si acceptance_rate < 70%, debes ser más conservador
PAPERLESS_AI_SUGGEST_THRESHOLD=0.70
```

---

## Verificación de Instalación {#verificacion}

### Checklist de Verificación

#### 1. Servicios Base

```bash
# Verificar Redis
redis-cli ping  # Debe responder "PONG"

# Verificar PostgreSQL
psql -U paperless -c "SELECT version();"

# Verificar Tesseract
tesseract --version
tesseract --list-langs  # Debe incluir eng, spa, etc.
```

#### 2. Dependencias Python

```bash
# Docker
docker exec intellidocs-webserver python -c "
import torch
import transformers
import spacy
import cv2
import pytesseract
print('✓ Todas las dependencias están instaladas')
"

# Bare metal
python -c "
import torch
import transformers
import spacy
import cv2
import pytesseract
print('✓ Todas las dependencias están instaladas')
"
```

#### 3. Modelos ML

```bash
# Verificar modelo BERT
python -c "
from transformers import AutoTokenizer, AutoModel
model_name = 'distilbert-base-uncased'
tokenizer = AutoTokenizer.from_pretrained(model_name)
model = AutoModel.from_pretrained(model_name)
print(f'✓ Modelo BERT {model_name} cargado correctamente')
"

# Verificar modelo spaCy
python -c "
import spacy
nlp = spacy.load('en_core_web_sm')
print('✓ Modelo spaCy cargado correctamente')
"
```

#### 4. AI Scanner

```bash
# Verificar que AI Scanner está habilitado
docker exec intellidocs-webserver python manage.py shell -c "
from django.conf import settings
print(f'AI Scanner enabled: {settings.ENABLE_AI_SCANNER}')
print(f'ML features enabled: {settings.ENABLE_ML_FEATURES}')
print(f'Advanced OCR enabled: {settings.ENABLE_ADVANCED_OCR}')
"
```

#### 5. Test de Escaneo

Sube un documento de prueba y verifica los logs:

```bash
# Ver logs del AI Scanner
docker compose logs -f webserver | grep "AI Scanner"

# Deberías ver líneas como:
# [INFO] AI Scanner: Starting scan for document 123
# [INFO] AI Scanner: Suggested 3 tags with confidence 0.82
# [INFO] AI Scanner: Auto-applied 2 tags (confidence >= 0.80)
```

### Script de Verificación Automática

Guarda este script como `verify_ai_scanner.sh`:

```bash
#!/bin/bash

echo "=== Verificación AI Scanner ==="
echo ""

# Colores
GREEN='\033[0;32m'
RED='\033[0;31m'
NC='\033[0m'

check_service() {
    if $1; then
        echo -e "${GREEN}✓${NC} $2"
        return 0
    else
        echo -e "${RED}✗${NC} $2"
        return 1
    fi
}

# 1. Redis
check_service "redis-cli ping > /dev/null 2>&1" "Redis"

# 2. PostgreSQL (ajustar según tu config)
check_service "psql -U paperless -c 'SELECT 1' > /dev/null 2>&1" "PostgreSQL"

# 3. Tesseract
check_service "tesseract --version > /dev/null 2>&1" "Tesseract OCR"

# 4. Contenedores Docker
if command -v docker &> /dev/null; then
    check_service "docker ps | grep intellidocs-webserver > /dev/null" "IntelliDocs Container"
fi

# 5. Python dependencies
PYTHON_CHECK='python -c "import torch, transformers, spacy, cv2" 2>&1'
check_service "$PYTHON_CHECK" "Dependencias Python"

# 6. Modelos ML
SPACY_CHECK='python -c "import spacy; spacy.load(\"en_core_web_sm\")" 2>&1'
check_service "$SPACY_CHECK" "Modelo spaCy"

echo ""
echo "=== Verificación completada ==="
```

Ejecutar:
```bash
chmod +x verify_ai_scanner.sh
./verify_ai_scanner.sh
```

### Troubleshooting de Instalación

Si encuentras problemas, consulta:
- [Guía de Troubleshooting](ai-scanner-troubleshooting.md)
- [Logs del sistema](#logs)
- [Issues comunes](#issues-comunes)

### Próximos Pasos

Una vez verificada la instalación:

1. **Configurar umbrales** según tu caso de uso
2. **Entrenar modelos custom** con tus documentos (opcional)
3. **Monitorear rendimiento** con métricas
4. **Optimizar configuración** según la [Guía de Optimización](ai-scanner-optimization.md)

---

## Logs y Monitoreo {#logs}

### Ubicación de Logs

**Docker:**
```bash
# Logs del webserver
docker compose logs -f webserver

# Logs del worker
docker compose logs -f worker

# Logs específicos del AI Scanner
docker compose logs webserver | grep "AI Scanner"
```

**Bare Metal:**
```bash
# Logs de Django
tail -f /var/log/paperless/paperless.log

# Logs de Celery
tail -f /var/log/paperless/celery.log
```

### Niveles de Log

Configurar el nivel de detalle en logs:

```bash
# Logs detallados (desarrollo)
PAPERLESS_LOGGING_LEVEL=DEBUG

# Logs estándar (producción)
PAPERLESS_LOGGING_LEVEL=INFO

# Solo errores
PAPERLESS_LOGGING_LEVEL=ERROR
```

### Métricas Importantes

Monitorear estas métricas:
- Tiempo de escaneo por documento
- Tasa de auto-aplicación vs sugerencias
- Precisión de sugerencias aceptadas
- Uso de memoria/CPU durante escaneo
- Tasa de errores en AI Scanner

---

## Soporte

### Documentación Adicional
- [Troubleshooting Guide](ai-scanner-troubleshooting.md)
- [Optimization Guide](ai-scanner-optimization.md)
- [Main Documentation](../index.md)

### Recursos
- [GitHub Repository](https://github.com/dawnsystem/IntelliDocs-ngx)
- [Issue Tracker](https://github.com/dawnsystem/IntelliDocs-ngx/issues)
- [AI Scanner Implementation](../../AI_SCANNER_IMPLEMENTATION.md)

### Contribuir
Si encuentras errores o tienes sugerencias de mejora, por favor abre un issue o pull request en GitHub.
