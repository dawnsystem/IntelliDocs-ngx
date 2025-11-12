# AI Scanner - Guía de Optimización y Performance

Esta guía proporciona estrategias y best practices para optimizar el rendimiento del sistema AI Scanner en IntelliDocs.

## Tabla de Contenidos

- [Overview de Performance](#overview)
- [Optimización de Hardware](#hardware)
- [Optimización de Software](#software)
- [Optimización de Modelos ML](#modelos)
- [Optimización de Base de Datos](#database)
- [Monitoreo y Métricas](#monitoring)
- [Best Practices](#best-practices)
- [Casos de Uso Específicos](#casos-uso)

---

## Overview de Performance {#overview}

### Benchmarks de Referencia

Tiempos típicos de procesamiento por documento (sin GPU):

| Componente | Tiempo Promedio | % del Total |
|-----------|----------------|-------------|
| Carga de modelos (primera vez) | 3-5s | - |
| Extracción OCR | 2-8s | 20-30% |
| Clasificación BERT | 8-15s | 40-50% |
| Extracción NER | 3-7s | 15-25% |
| Sugerencia de tags | 1-2s | 5-10% |
| Aplicación de resultados | 0.5-1s | 2-5% |
| **TOTAL por documento** | **15-35s** | **100%** |

### Mejoras Esperadas con Optimización

| Optimización | Mejora Esperada | Complejidad |
|-------------|-----------------|-------------|
| GPU NVIDIA | **10-20x más rápido** | Media |
| Modelo distilbert | 30-40% más rápido | Baja |
| Caché de embeddings | 50-60% más rápido | Media |
| Batch processing | 2-3x más rápido | Alta |
| Índices DB optimizados | 20-30% más rápido | Baja |
| Redis tuning | 10-15% más rápido | Baja |

### Identificar Cuellos de Botella

Ejecutar profiler:

```bash
# Analizar un documento específico
docker exec intellidocs-webserver python manage.py profile_ai_scanner \
    --document-id 123 \
    --output /tmp/profile.txt

# Ver reporte
docker exec intellidocs-webserver cat /tmp/profile.txt
```

Salida de ejemplo:
```
AI Scanner Performance Profile
================================
Document ID: 123
Total time: 28.4 seconds

Breakdown:
  1. Load models: 2.3s (8%)
  2. OCR extraction: 5.1s (18%)
  3. NER extraction: 6.8s (24%)
  4. BERT classification: 11.2s (39%)  ← BOTTLENECK
  5. Tag suggestion: 1.9s (7%)
  6. Apply results: 1.1s (4%)

Top Recommendations:
  ✓ Enable GPU for 10-15x speedup
  ✓ Use distilbert for 30-40% speedup
  ✓ Increase batch size if processing multiple docs
```

---

## Optimización de Hardware {#hardware}

### 1. Habilitar GPU (Máxima Prioridad)

**Mejora esperada:** 10-20x más rápido en BERT/NER

#### Requisitos:
- NVIDIA GPU con CUDA 11.x o superior
- nvidia-docker instalado
- Drivers NVIDIA actualizados

#### Configuración Docker:

```yaml
# docker-compose.yml
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

#### Configuración de ambiente:

```bash
# .env
PAPERLESS_USE_GPU=true

# Opcional: seleccionar GPU específica
CUDA_VISIBLE_DEVICES=0  # Primera GPU
```

#### Verificar:

```bash
# Ver GPUs disponibles
docker exec intellidocs-webserver nvidia-smi

# Verificar PyTorch ve la GPU
docker exec intellidocs-webserver python -c "
import torch
print(f'CUDA available: {torch.cuda.is_available()}')
print(f'CUDA device: {torch.cuda.get_device_name(0)}')
print(f'CUDA version: {torch.version.cuda}')
"
```

#### Benchmark GPU vs CPU:

```bash
# Ejecutar benchmark
docker exec intellidocs-webserver python manage.py benchmark_ai_scanner \
    --iterations 10 \
    --compare-gpu-cpu

# Ejemplo de salida:
# CPU average: 28.4s per document
# GPU average: 2.1s per document
# Speedup: 13.5x
```

### 2. Optimizar RAM

**Requisitos según configuración:**

| Configuración | RAM Mínima | RAM Recomendada |
|--------------|-----------|----------------|
| Solo AI Scanner básico | 4 GB | 8 GB |
| + OCR avanzado | 6 GB | 10 GB |
| + GPU habilitada | 8 GB | 12 GB |
| Producción alta carga | 12 GB | 16+ GB |

#### Configurar límites Docker:

```yaml
# docker-compose.yml
services:
  webserver:
    deploy:
      resources:
        limits:
          memory: 8G
        reservations:
          memory: 4G
```

#### Monitorear uso:

```bash
# En tiempo real
docker stats intellidocs-webserver

# Memoria máxima usada
docker inspect intellidocs-webserver | grep -i memory

# Historial (requiere monitoring)
docker exec intellidocs-webserver python manage.py memory_usage_report
```

#### Optimizar uso de RAM:

```bash
# 1. Reducir workers si RAM limitada
PAPERLESS_TASK_WORKERS=2  # En lugar de 4

# 2. Deshabilitar componentes no usados
PAPERLESS_ENABLE_TABLE_EXTRACTION=false  # Si no necesitas tablas
PAPERLESS_ENABLE_HANDWRITING_RECOGNITION=false  # Si no hay manuscritos

# 3. Usar modelos pequeños
PAPERLESS_ML_CLASSIFIER_MODEL=distilbert-base-uncased
PAPERLESS_NER_MODEL=en_core_web_sm
```

### 3. Optimizar CPU

#### Configurar cores Docker:

```yaml
# docker-compose.yml
services:
  webserver:
    deploy:
      resources:
        limits:
          cpus: '4.0'
```

#### Balancear workers:

```bash
# Regla general: 1-2 workers por 2 CPU cores
# Sistema con 4 cores:
PAPERLESS_TASK_WORKERS=2
CELERY_WORKER_CONCURRENCY=2

# Sistema con 8 cores:
PAPERLESS_TASK_WORKERS=4
CELERY_WORKER_CONCURRENCY=2
```

#### Prioridad de procesos:

```bash
# Aumentar prioridad del worker (solo si es único servicio importante)
docker exec intellidocs-webserver renice -n -5 -p $(pidof celery)
```

### 4. Optimizar Almacenamiento

#### SSD vs HDD:

```bash
# Caché ML en SSD (mucho más rápido)
PAPERLESS_ML_MODEL_CACHE=/mnt/ssd/ml_cache

# Documentos pueden estar en HDD
PAPERLESS_MEDIA_ROOT=/mnt/hdd/media
```

#### Benchmark I/O:

```bash
# Medir velocidad de lectura
docker exec intellidocs-webserver python manage.py benchmark_io \
    --test-file /usr/src/paperless/media/documents/test.pdf

# Ejemplo de salida:
# Read speed: 450 MB/s (SSD)
# Read speed: 80 MB/s (HDD)
```

---

## Optimización de Software {#software}

### 1. Selección de Modelos ML

#### Modelos BERT (Clasificación):

| Modelo | Tamaño | Velocidad | Precisión | Uso Recomendado |
|--------|--------|-----------|-----------|----------------|
| distilbert-base-uncased | 66M | ⚡⚡⚡ Rápido | ⭐⭐ Buena | **Uso general, alta carga** |
| bert-base-uncased | 110M | ⚡⚡ Medio | ⭐⭐⭐ Muy buena | Balanceado |
| bert-base-multilingual | 110M | ⚡⚡ Medio | ⭐⭐⭐ Muy buena | **Múltiples idiomas** |
| bert-large-uncased | 340M | ⚡ Lento | ⭐⭐⭐⭐ Excelente | Solo con GPU, máxima precisión |

**Configuración recomendada:**

```bash
# Alta carga, múltiples documentos/día
PAPERLESS_ML_CLASSIFIER_MODEL=distilbert-base-uncased

# Documentos complejos, precisión crítica
PAPERLESS_ML_CLASSIFIER_MODEL=bert-base-uncased

# Documentos en varios idiomas
PAPERLESS_ML_CLASSIFIER_MODEL=bert-base-multilingual-cased
```

#### Modelos spaCy (NER):

| Modelo | Tamaño | Velocidad | Precisión | Uso Recomendado |
|--------|--------|-----------|-----------|----------------|
| en_core_web_sm | 12 MB | ⚡⚡⚡ Rápido | ⭐⭐ Básica | **Uso general** |
| en_core_web_md | 40 MB | ⚡⚡ Medio | ⭐⭐⭐ Buena | Balanceado |
| en_core_web_lg | 560 MB | ⚡ Lento | ⭐⭐⭐⭐ Excelente | Alta precisión en NER |

**Configuración recomendada:**

```bash
# Uso general (inglés)
PAPERLESS_NER_MODEL=en_core_web_sm

# Español
PAPERLESS_NER_MODEL=es_core_news_sm

# Alta precisión (con GPU)
PAPERLESS_NER_MODEL=en_core_web_lg
```

### 2. Ajuste de Umbrales

Optimizar balance entre automatización y precisión:

#### Perfiles Pre-configurados:

**Conservador (Máxima Precisión):**
```bash
PAPERLESS_AI_AUTO_APPLY_THRESHOLD=0.95  # Solo aplicar si muy seguro
PAPERLESS_AI_SUGGEST_THRESHOLD=0.80     # Sugerir con alta confianza
```
- **Pros:** Errores mínimos, alta precisión
- **Contras:** Requiere más revisión manual
- **Uso:** Documentos legales, financieros críticos

**Balanceado (Recomendado):**
```bash
PAPERLESS_AI_AUTO_APPLY_THRESHOLD=0.80
PAPERLESS_AI_SUGGEST_THRESHOLD=0.60
```
- **Pros:** Buen balance automatización/precisión
- **Contras:** Errores ocasionales
- **Uso:** Uso general, la mayoría de casos

**Agresivo (Máxima Automatización):**
```bash
PAPERLESS_AI_AUTO_APPLY_THRESHOLD=0.70
PAPERLESS_AI_SUGGEST_THRESHOLD=0.50
```
- **Pros:** Máxima automatización
- **Contras:** Más errores, requiere corrección
- **Uso:** Volumen muy alto, documentos simples

#### Ajuste Dinámico:

```bash
# Analizar precisión actual
docker exec intellidocs-webserver python manage.py analyze_ai_accuracy --days 30

# Ejemplo de salida:
# Auto-applied: 450 suggestions, 94% accuracy
# Suggested: 180 suggestions, 81% acceptance rate
# 
# Recommendations:
# - Current thresholds are optimal
# - Consider lowering auto_apply to 0.75 for more automation
```

### 3. Caché y Performance

#### Habilitar Caché de Embeddings:

```bash
# Cachea vectores de documentos ya procesados
PAPERLESS_ENABLE_EMBEDDING_CACHE=true
PAPERLESS_EMBEDDING_CACHE_SIZE=1000  # Número de documentos en caché

# Ubicación del caché (usar SSD)
PAPERLESS_EMBEDDING_CACHE_DIR=/usr/src/paperless/ml_cache/embeddings
```

**Mejora esperada:** 50-60% más rápido para documentos similares

#### Optimizar Redis:

```bash
# Aumentar memoria de Redis
REDIS_MAXMEMORY=2gb

# Política de eviction
REDIS_MAXMEMORY_POLICY=allkeys-lru

# Persistencia (balance performance/durabilidad)
REDIS_APPENDONLY=no  # Mejor performance, menos durabilidad
```

#### Pre-cargar Modelos:

```bash
# Cargar modelos al inicio (no lazy loading)
PAPERLESS_PRELOAD_ML_MODELS=true
```

**Pros:** Primera consulta más rápida  
**Contras:** Inicio más lento, más RAM

### 4. Batch Processing

Para volúmenes altos:

```bash
# Procesar documentos en lotes
PAPERLESS_AI_BATCH_SIZE=10  # Procesar 10 docs juntos
PAPERLESS_AI_BATCH_TIMEOUT=300  # Max 5 minutos por lote

# Activar solo si procesas muchos docs simultáneamente
```

**Mejora esperada:** 2-3x más rápido para lotes grandes

#### Implementar:

```python
# Custom management command
# src/documents/management/commands/batch_scan.py

from django.core.management.base import BaseCommand
from documents.models import Document
from documents.ai_scanner import AIDocumentScanner

class Command(BaseCommand):
    def handle(self, *args, **options):
        scanner = AIDocumentScanner()
        
        # Obtener documentos sin escanear
        docs = Document.objects.filter(
            _ai_scanned=False
        )[:100]
        
        # Procesar en lotes de 10
        for i in range(0, len(docs), 10):
            batch = docs[i:i+10]
            scanner.scan_batch(batch)
```

---

## Optimización de Modelos ML {#modelos}

### 1. Quantization (Reducción de Precisión)

Reduce tamaño y aumenta velocidad con pérdida mínima de precisión:

```bash
# Habilitar quantization INT8
PAPERLESS_ML_QUANTIZATION=int8

# O FP16 (solo GPU)
PAPERLESS_ML_QUANTIZATION=fp16
```

**Mejora esperada:**
- INT8: 2-3x más rápido, 75% menos memoria
- FP16: 1.5-2x más rápido, 50% menos memoria

#### Aplicar quantization:

```bash
# Convertir modelo existente
docker exec intellidocs-webserver python manage.py quantize_model \
    --model distilbert-base-uncased \
    --quantization int8 \
    --output /usr/src/paperless/ml_cache/distilbert-int8

# Usar modelo quantizado
PAPERLESS_ML_CLASSIFIER_MODEL=/usr/src/paperless/ml_cache/distilbert-int8
```

### 2. Pruning (Poda de Neuronas)

Elimina conexiones menos importantes:

```bash
# Habilitar pruning (reduce 30-40% tamaño)
PAPERLESS_ML_PRUNING=true
PAPERLESS_ML_PRUNING_RATIO=0.3  # Podar 30% de conexiones
```

**Mejora esperada:** 20-30% más rápido, pérdida <2% precisión

### 3. Knowledge Distillation

Entrenar modelo pequeño que imita modelo grande:

```bash
# Entrenar modelo distilled custom
docker exec intellidocs-webserver python manage.py distill_model \
    --teacher bert-large-uncased \
    --student distilbert-base-uncased \
    --training-data /tmp/training_data.json \
    --epochs 5 \
    --output /usr/src/paperless/ml_cache/custom-distilled
```

**Mejora esperada:** Precisión similar a modelo grande, velocidad de modelo pequeño

### 4. ONNX Runtime

Convertir modelos a formato ONNX optimizado:

```bash
# Habilitar ONNX runtime
PAPERLESS_USE_ONNX_RUNTIME=true

# Convertir modelo
docker exec intellidocs-webserver python manage.py convert_to_onnx \
    --model distilbert-base-uncased \
    --output /usr/src/paperless/ml_cache/distilbert.onnx
```

**Mejora esperada:** 20-40% más rápido en CPU

---

## Optimización de Base de Datos {#database}

### 1. Índices Optimizados

Crear índices para queries frecuentes:

```sql
-- Índice compuesto para búsqueda de documentos por tipo y fecha
CREATE INDEX idx_doc_type_created ON documents_document(document_type_id, created);

-- Índice para etiquetas
CREATE INDEX idx_doc_tags ON documents_document_tags(document_id, tag_id);

-- Índice para correspondents
CREATE INDEX idx_doc_correspondent ON documents_document(correspondent_id);

-- Índice para AI suggestions (si se almacenan)
CREATE INDEX idx_ai_suggestions ON documents_ai_suggestion(document_id, confidence);
```

**Aplicar índices:**

```bash
# Docker
docker exec intellidocs-webserver python manage.py dbshell < optimize_indexes.sql

# O crear migración
docker exec intellidocs-webserver python manage.py makemigrations --empty documents
# Editar migración para añadir índices
```

### 2. Vacuum y Analyze (PostgreSQL)

Optimizar tablas regularmente:

```bash
# Manual
docker exec intellidocs-db psql -U paperless -c "VACUUM ANALYZE;"

# Automático (cron diario)
0 2 * * * docker exec intellidocs-db psql -U paperless -c "VACUUM ANALYZE;"
```

### 3. Connection Pooling

Optimizar conexiones a DB:

```bash
# Usar PgBouncer
PAPERLESS_DB_POOLING=true
PAPERLESS_DB_POOL_SIZE=20
PAPERLESS_DB_MAX_OVERFLOW=10
```

### 4. Query Optimization

Optimizar queries del AI Scanner:

```python
# Malo: N+1 queries
for doc in Document.objects.all():
    doc.tags.all()  # Query por cada documento

# Bueno: Prefetch
docs = Document.objects.prefetch_related('tags', 'correspondent', 'document_type')
for doc in docs:
    doc.tags.all()  # Sin queries adicionales
```

---

## Monitoreo y Métricas {#monitoring}

### 1. Métricas Clave

Monitorear estas métricas:

| Métrica | Objetivo | Crítico si |
|---------|----------|-----------|
| Tiempo de escaneo | <15s | >30s |
| CPU usage | <70% | >90% |
| Memoria usage | <80% | >95% |
| GPU usage (si aplica) | 50-80% | <20% o >95% |
| Tasa de auto-aplicación | >70% | <50% |
| Precisión de sugerencias | >90% | <80% |
| Cola de procesamiento | <10 docs | >50 docs |

### 2. Dashboard de Monitoreo

Configurar Prometheus + Grafana:

```yaml
# docker-compose.yml
services:
  prometheus:
    image: prom/prometheus
    volumes:
      - ./prometheus.yml:/etc/prometheus/prometheus.yml
    ports:
      - "9090:9090"
  
  grafana:
    image: grafana/grafana
    ports:
      - "3000:3000"
    depends_on:
      - prometheus
```

#### Métricas exportadas:

```bash
# Habilitar exportador de métricas
PAPERLESS_ENABLE_METRICS=true
PAPERLESS_METRICS_PORT=9100

# Métricas disponibles en http://localhost:9100/metrics
```

### 3. Alertas

Configurar alertas automáticas:

```yaml
# prometheus_alerts.yml
groups:
  - name: ai_scanner_alerts
    rules:
      - alert: SlowAIScan
        expr: ai_scanner_duration_seconds > 30
        for: 5m
        annotations:
          summary: "AI Scanner muy lento"
          
      - alert: HighErrorRate
        expr: ai_scanner_error_rate > 0.05
        for: 10m
        annotations:
          summary: "Tasa de errores alta (>5%)"
          
      - alert: HighMemoryUsage
        expr: container_memory_usage_bytes / container_spec_memory_limit_bytes > 0.9
        for: 5m
        annotations:
          summary: "Uso de memoria crítico (>90%)"
```

### 4. Logs Estructurados

Mejorar logging para análisis:

```bash
# Habilitar logs en JSON
PAPERLESS_LOG_FORMAT=json

# Enviar a sistema centralizado
PAPERLESS_LOG_DESTINATION=syslog://logserver:514
```

---

## Best Practices {#best-practices}

### 1. Configuración Inicial

**Setup checklist:**

- [ ] GPU habilitada si está disponible
- [ ] Modelo distilbert para inicio rápido
- [ ] Umbrales balanceados (0.80/0.60)
- [ ] Caché ML en volumen persistente
- [ ] Índices de DB creados
- [ ] Redis optimizado
- [ ] Monitoreo básico activo
- [ ] Logs configurados

### 2. Entrenamiento de Modelos

**Cuando entrenar modelo custom:**

✅ **Sí entrenar si:**
- Tienes >100 documentos ya clasificados
- Precisión actual <80%
- Documentos muy específicos de tu dominio
- Múltiples idiomas no soportados

❌ **No entrenar si:**
- Pocos documentos (<50)
- Precisión actual >90%
- Documentos genéricos
- Falta expertise en ML

**Proceso recomendado:**

1. Recopilar ≥100 documentos por tipo
2. Validar calidad de etiquetas existentes
3. Entrenar con 80% train / 20% validation
4. Evaluar en conjunto de prueba separado
5. Comparar con modelo base
6. Deployer solo si mejora >5% precisión

### 3. Mantenimiento Regular

**Tareas semanales:**
```bash
# Limpiar caché antiguo
docker exec intellidocs-webserver python manage.py clean_ml_cache --days 30

# Revisar logs de errores
docker compose logs webserver | grep ERROR | tail -50

# Verificar métricas
docker exec intellidocs-webserver python manage.py ai_scanner_stats
```

**Tareas mensuales:**
```bash
# Analizar precisión
docker exec intellidocs-webserver python manage.py analyze_ai_accuracy --days 30

# Optimizar DB
docker exec intellidocs-db psql -U paperless -c "VACUUM ANALYZE;"

# Revisar uso de recursos
docker stats --no-stream

# Actualizar modelos si disponibles
docker exec intellidocs-webserver pip list --outdated | grep -i "transformers\|spacy\|torch"
```

### 4. Escalabilidad

**Escalar horizontalmente:**

Para >1000 documentos/día:

```yaml
# docker-compose.yml
services:
  webserver:
    # ...
  
  worker-1:
    <<: *webserver
    command: celery -A paperless worker -l INFO --hostname=worker1@%h
  
  worker-2:
    <<: *webserver
    command: celery -A paperless worker -l INFO --hostname=worker2@%h
  
  worker-3:
    <<: *webserver
    command: celery -A paperless worker -l INFO --hostname=worker3@%h
```

**Balanceo de carga:**

```bash
# Distribuir carga según tipo
PAPERLESS_WORKER_1_QUEUES=classification
PAPERLESS_WORKER_2_QUEUES=ner,ocr
PAPERLESS_WORKER_3_QUEUES=default
```

### 5. Seguridad y Privacy

**Consideraciones:**

✅ **Seguro:**
- Todos los modelos locales
- No se envían datos a servicios externos
- Embeddings en caché local
- Logs sin contenido sensible

⚠️ **Atención:**
- GPU compartida (si multi-tenant)
- Caché puede contener fragmentos de texto
- Logs de debug pueden exponer metadatos

**Configuración segura:**

```bash
# No usar debug en producción
PAPERLESS_DEBUG=false

# Sanitizar logs
PAPERLESS_LOG_SANITIZE=true

# Encriptar caché
PAPERLESS_ENCRYPT_ML_CACHE=true
PAPERLESS_ML_CACHE_KEY=tu_clave_secreta
```

---

## Casos de Uso Específicos {#casos-uso}

### 1. Volumen Bajo (<100 docs/mes)

**Configuración óptima:**

```bash
# Priorizar facilidad sobre performance
PAPERLESS_ENABLE_AI_SCANNER=true
PAPERLESS_ENABLE_ML_FEATURES=true
PAPERLESS_ENABLE_ADVANCED_OCR=false  # No necesario

# Modelos pequeños
PAPERLESS_ML_CLASSIFIER_MODEL=distilbert-base-uncased
PAPERLESS_NER_MODEL=en_core_web_sm

# Sin GPU necesaria
PAPERLESS_USE_GPU=false

# Workers mínimos
PAPERLESS_TASK_WORKERS=1

# Hardware:
# - 2 CPU cores
# - 4 GB RAM
# - 10 GB storage
```

### 2. Volumen Medio (100-1000 docs/mes)

**Configuración óptima:**

```bash
# Balance performance/recursos
PAPERLESS_ENABLE_AI_SCANNER=true
PAPERLESS_ENABLE_ML_FEATURES=true
PAPERLESS_ENABLE_ADVANCED_OCR=true

# Modelos balanceados
PAPERLESS_ML_CLASSIFIER_MODEL=distilbert-base-uncased
PAPERLESS_NER_MODEL=en_core_web_md

# GPU recomendada
PAPERLESS_USE_GPU=true

# Workers según carga
PAPERLESS_TASK_WORKERS=2-4

# Hardware:
# - 4-8 CPU cores
# - 8-16 GB RAM
# - 20 GB storage
# - GPU: GTX 1660 o superior
```

### 3. Volumen Alto (>1000 docs/mes)

**Configuración óptima:**

```bash
# Máxima performance
PAPERLESS_ENABLE_AI_SCANNER=true
PAPERLESS_ENABLE_ML_FEATURES=true
PAPERLESS_ENABLE_ADVANCED_OCR=true

# Modelos optimizados
PAPERLESS_ML_CLASSIFIER_MODEL=distilbert-base-uncased
PAPERLESS_NER_MODEL=en_core_web_sm  # Velocidad > precisión
PAPERLESS_USE_ONNX_RUNTIME=true
PAPERLESS_ML_QUANTIZATION=int8

# GPU obligatoria
PAPERLESS_USE_GPU=true

# Múltiples workers
PAPERLESS_TASK_WORKERS=8

# Batch processing
PAPERLESS_AI_BATCH_SIZE=10

# Hardware:
# - 8+ CPU cores
# - 16+ GB RAM
# - 50+ GB storage SSD
# - GPU: RTX 3060 o superior
```

### 4. Documentos Multilíngües

**Configuración óptima:**

```bash
# Modelos multilingües
PAPERLESS_ML_CLASSIFIER_MODEL=bert-base-multilingual-cased
PAPERLESS_NER_MODEL=xx_ent_wiki_sm

# OCR multi-idioma
PAPERLESS_OCR_LANGUAGE=eng+spa+fra+deu

# Instalar modelos spaCy por idioma
# en_core_web_sm (inglés)
# es_core_news_sm (español)
# fr_core_news_sm (francés)
# de_core_news_sm (alemán)
```

### 5. Documentos Técnicos/Especializados

**Configuración óptima:**

```bash
# Modelos grandes para máxima precisión
PAPERLESS_ML_CLASSIFIER_MODEL=bert-large-uncased
PAPERLESS_NER_MODEL=en_core_web_lg

# Entrenar modelo custom
# (ver guía de training)

# Umbrales conservadores
PAPERLESS_AI_AUTO_APPLY_THRESHOLD=0.90
PAPERLESS_AI_SUGGEST_THRESHOLD=0.75

# GPU obligatoria
PAPERLESS_USE_GPU=true
```

---

## Benchmark y Testing

### Ejecutar Benchmark Completo

```bash
# Benchmark end-to-end
docker exec intellidocs-webserver python manage.py benchmark_ai_scanner \
    --iterations 50 \
    --document-types invoice,contract,receipt \
    --output /tmp/benchmark_results.json

# Ver resultados
docker exec intellidocs-webserver cat /tmp/benchmark_results.json
```

### Benchmark por Componente

```bash
# Solo BERT
docker exec intellidocs-webserver python manage.py benchmark_component \
    --component bert \
    --iterations 100

# Solo NER
docker exec intellidocs-webserver python manage.py benchmark_component \
    --component ner \
    --iterations 100

# Solo OCR
docker exec intellidocs-webserver python manage.py benchmark_component \
    --component ocr \
    --iterations 50
```

### Comparar Configuraciones

```bash
# A/B test entre configuraciones
docker exec intellidocs-webserver python manage.py ab_test \
    --config-a distilbert \
    --config-b bert-base \
    --documents 100 \
    --output /tmp/ab_test.json
```

---

## Recursos Adicionales

### Documentación
- [Setup Guide](ai-scanner-setup.md)
- [Troubleshooting Guide](ai-scanner-troubleshooting.md)
- [Main Documentation](../index.md)

### Herramientas
- [Model Hub (HuggingFace)](https://huggingface.co/models)
- [spaCy Models](https://spacy.io/models)
- [ONNX Runtime](https://onnxruntime.ai/)

### Comunidad
- [GitHub Discussions](https://github.com/dawnsystem/IntelliDocs-ngx/discussions)
- [Issue Tracker](https://github.com/dawnsystem/IntelliDocs-ngx/issues)

---

## Resumen de Optimizaciones

| Optimización | Complejidad | Mejora | Prioridad |
|-------------|-------------|--------|-----------|
| **Habilitar GPU** | Media | 10-20x | 🔴 Alta |
| **Usar distilbert** | Baja | 30-40% | 🔴 Alta |
| **Optimizar umbrales** | Baja | Variable | 🔴 Alta |
| **Índices DB** | Baja | 20-30% | 🟡 Media |
| **Caché embeddings** | Media | 50-60% | 🟡 Media |
| **Batch processing** | Alta | 2-3x | 🟢 Baja |
| **ONNX Runtime** | Media | 20-40% | 🟢 Baja |
| **Quantization** | Alta | 2-3x | 🟢 Baja |

**Recomendación:** Implementar en orden de prioridad para máximo impacto con mínimo esfuerzo.
