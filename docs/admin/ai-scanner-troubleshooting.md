# AI Scanner - Guía de Troubleshooting

Esta guía proporciona soluciones a los problemas más comunes del sistema AI Scanner en IntelliDocs.

## Tabla de Contenidos

- [Problemas de Instalación](#instalacion)
- [Problemas de Configuración](#configuracion)
- [Problemas de Rendimiento](#rendimiento)
- [Problemas con Modelos ML](#modelos-ml)
- [Problemas de Escaneo](#escaneo)
- [Problemas de OCR](#ocr)
- [Errores Comunes](#errores-comunes)
- [Diagnóstico Avanzado](#diagnostico)

---

## Problemas de Instalación {#instalacion}

### El AI Scanner no se inicia

**Síntomas:**
- Los documentos se procesan pero no se aplican sugerencias
- No aparecen logs de "AI Scanner" en los registros
- La variable `ENABLE_AI_SCANNER` parece ignorada

**Soluciones:**

1. **Verificar que está habilitado:**
```bash
# Docker
docker exec intellidocs-webserver python manage.py shell -c "
from django.conf import settings
print(f'AI Scanner: {getattr(settings, \"ENABLE_AI_SCANNER\", \"NOT SET\")}')
"

# Bare metal
python manage.py shell -c "
from django.conf import settings
print(f'AI Scanner: {getattr(settings, \"ENABLE_AI_SCANNER\", \"NOT SET\")}')
"
```

2. **Verificar variables de entorno:**
```bash
# Docker
docker exec intellidocs-webserver env | grep PAPERLESS_ENABLE_AI_SCANNER

# Debe mostrar: PAPERLESS_ENABLE_AI_SCANNER=true
```

3. **Reiniciar servicios:**
```bash
# Docker
docker compose restart webserver worker

# Bare metal
# Reiniciar Celery y Django
```

4. **Verificar logs de inicio:**
```bash
docker compose logs webserver | grep -i "ai scanner\|ml features"
```

### Error: "ModuleNotFoundError: No module named 'transformers'"

**Causa:** Dependencias ML no instaladas.

**Solución:**

**Docker:**
```bash
# Reconstruir imagen
docker compose down
docker compose build --no-cache
docker compose up -d
```

**Bare metal:**
```bash
# Reinstalar dependencias
pip install -r requirements.txt

# O instalar manualmente
pip install torch>=2.0.0 transformers>=4.30.0 spacy>=3.5.0
```

### Error: "OSError: Can't load tokenizer for 'distilbert-base-uncased'"

**Causa:** Modelo BERT no descargado o caché corrupto.

**Solución:**

1. **Limpiar caché:**
```bash
# Docker
docker exec intellidocs-webserver rm -rf /usr/src/paperless/ml_cache/*

# Bare metal
rm -rf $PAPERLESS_ML_MODEL_CACHE/*
```

2. **Descargar modelo manualmente:**
```bash
# Docker
docker exec intellidocs-webserver python -c "
from transformers import AutoTokenizer, AutoModel
model = 'distilbert-base-uncased'
AutoTokenizer.from_pretrained(model)
AutoModel.from_pretrained(model)
print('✓ Modelo descargado')
"
```

3. **Verificar conectividad:**
```bash
# El sistema necesita acceso a huggingface.co
curl -I https://huggingface.co
```

### Error: "Can't find model 'en_core_web_sm'"

**Causa:** Modelo spaCy para NER no instalado.

**Solución:**

```bash
# Docker
docker exec intellidocs-webserver python -m spacy download en_core_web_sm

# Bare metal
python -m spacy download en_core_web_sm

# Para español
python -m spacy download es_core_news_sm
```

**Verificar instalación:**
```bash
python -c "import spacy; nlp = spacy.load('en_core_web_sm'); print('✓ OK')"
```

---

## Problemas de Configuración {#configuracion}

### Las sugerencias no se aplican automáticamente

**Síntomas:**
- El AI Scanner detecta sugerencias
- Las sugerencias aparecen en logs con alta confianza (>0.80)
- Pero no se aplican al documento

**Causas y Soluciones:**

1. **Umbral muy alto:**
```bash
# Verificar umbral actual
docker exec intellidocs-webserver python manage.py shell -c "
from django.conf import settings
print(f'Auto-apply threshold: {settings.AI_AUTO_APPLY_THRESHOLD}')
"

# Si es >0.90, considera bajarlo
PAPERLESS_AI_AUTO_APPLY_THRESHOLD=0.80
```

2. **Modo "solo sugerencias":**
```bash
# Si el umbral está en 1.0, NUNCA se auto-aplica
# Cambiarlo a un valor razonable
PAPERLESS_AI_AUTO_APPLY_THRESHOLD=0.80
```

3. **Verificar que las sugerencias se generan:**
```bash
# Ver logs detallados
docker compose logs webserver | grep -A 5 "AI Scanner: Suggested"
```

### El AI Scanner procesa documentos muy lentamente

**Síntomas:**
- Escaneo tarda >30 segundos por documento
- Consumo alto de CPU/memoria
- Cola de procesamiento crece

**Ver sección:** [Problemas de Rendimiento](#rendimiento)

### Los tipos de documento no se detectan correctamente

**Síntomas:**
- Tipos de documento incorrectos o no detectados
- Confianza siempre baja (<0.60)

**Soluciones:**

1. **Entrenar modelo custom:**
   - Ver [Training de Modelos Custom](ai-scanner-setup.md#training-modelos-custom)
   - Necesitas al menos 10-20 documentos por tipo

2. **Ajustar modelo base:**
```bash
# Probar modelo multilingual si tienes documentos en varios idiomas
PAPERLESS_ML_CLASSIFIER_MODEL=bert-base-multilingual-cased
```

3. **Verificar contenido OCR:**
```bash
# El clasificador necesita texto OCR de calidad
docker exec intellidocs-webserver python manage.py shell -c "
from documents.models import Document
doc = Document.objects.last()
print(f'Content length: {len(doc.content)}')
print(f'First 500 chars: {doc.content[:500]}')
"

# Si el contenido está vacío o corrupto, el problema es OCR
```

### Las etiquetas sugeridas no son relevantes

**Síntomas:**
- Etiquetas genéricas o poco útiles
- Etiquetas duplicadas
- Etiquetas que no coinciden con el contenido

**Soluciones:**

1. **Mejorar matching rules:**
   - Ir a Admin → Tags → [Tu Tag]
   - Configurar "Matching" y "Matching Algorithm"
   - El AI Scanner usa estas reglas como base

2. **Ajustar extracción de entidades:**
```bash
# Usar modelo NER más grande
PAPERLESS_NER_MODEL=en_core_web_lg  # o es_core_news_lg

# Instalar el modelo
docker exec intellidocs-webserver python -m spacy download en_core_web_lg
```

3. **Revisar umbrales:**
```bash
# Aumentar umbral de sugerencias para mayor precisión
PAPERLESS_AI_SUGGEST_THRESHOLD=0.70
```

---

## Problemas de Rendimiento {#rendimiento}

### Escaneo muy lento (>30 segundos por documento)

**Diagnóstico:**

```bash
# Ver tiempo de procesamiento
docker compose logs webserver | grep "AI Scanner: Scan completed" | tail -20

# Ejemplo de salida:
# AI Scanner: Scan completed for document 123 in 45.2 seconds
```

**Soluciones por componente:**

#### 1. ML Classifier (BERT) lento

**Síntomas:** >15 segundos en clasificación

**Soluciones:**
```bash
# A. Usar modelo más pequeño
PAPERLESS_ML_CLASSIFIER_MODEL=distilbert-base-uncased

# B. Habilitar GPU (10-20x más rápido)
PAPERLESS_USE_GPU=true

# C. Reducir longitud de texto procesado
PAPERLESS_ML_MAX_TOKENS=512  # Default, puede bajarse a 256
```

#### 2. NER (spaCy) lento

**Síntomas:** >10 segundos en extracción de entidades

**Soluciones:**
```bash
# A. Usar modelo más pequeño
PAPERLESS_NER_MODEL=en_core_web_sm

# B. Limitar texto procesado
PAPERLESS_NER_MAX_CHARS=50000  # Procesar solo primeros 50k caracteres
```

#### 3. OCR Avanzado lento

**Síntomas:** >20 segundos en extracción de tablas

**Soluciones:**
```bash
# A. Deshabilitar funciones no necesarias
PAPERLESS_ENABLE_TABLE_EXTRACTION=false
PAPERLESS_ENABLE_HANDWRITING_RECOGNITION=false
PAPERLESS_ENABLE_FORM_DETECTION=false

# B. Ajustar calidad/velocidad de OCR
PAPERLESS_OCR_MODE=fast  # En lugar de 'accurate'
```

#### 4. Optimizar recursos

```bash
# A. Aumentar workers (si tienes RAM)
PAPERLESS_TASK_WORKERS=4

# B. Ajustar concurrencia Celery
CELERY_WORKER_CONCURRENCY=2

# C. Asignar más memoria al contenedor
# En docker-compose.yml:
services:
  webserver:
    deploy:
      resources:
        limits:
          memory: 4G  # Aumentar si es necesario
```

### Alto uso de memoria

**Síntomas:**
- OOMKilled (Out of Memory)
- Sistema lento o swap intenso
- Logs: "MemoryError" o "Killed"

**Diagnóstico:**
```bash
# Monitorear memoria en tiempo real
docker stats intellidocs-webserver

# Ver memoria máxima usada
docker inspect intellidocs-webserver | grep -i memory
```

**Soluciones:**

1. **Limitar carga de modelos:**
```bash
# No cargar todos los modelos simultáneamente
# Los modelos se cargan con "lazy loading"
# Asegurar que esta configuración está activa
```

2. **Reducir tamaño de modelos:**
```bash
# BERT
PAPERLESS_ML_CLASSIFIER_MODEL=distilbert-base-uncased  # ~250MB vs ~420MB

# spaCy
PAPERLESS_NER_MODEL=en_core_web_sm  # ~12MB vs ~560MB
```

3. **Limitar workers:**
```bash
# Menos workers = menos memoria
PAPERLESS_TASK_WORKERS=1
CELERY_WORKER_CONCURRENCY=1
```

4. **Procesamiento por lotes:**
```bash
# Procesar documentos en lotes pequeños
# En lugar de consumo masivo simultáneo
```

5. **Aumentar memoria disponible:**
```yaml
# docker-compose.yml
services:
  webserver:
    deploy:
      resources:
        limits:
          memory: 8G  # Aumentar según disponibilidad
        reservations:
          memory: 4G
```

### CPU al 100% constante

**Síntomas:**
- CPU saturada incluso sin documentos procesándose
- Sistema irresponsivo

**Causas comunes:**

1. **Bucle infinito en procesamiento:**
```bash
# Ver qué procesos consumen CPU
docker exec intellidocs-webserver top -b -n 1

# Verificar logs de errores
docker compose logs webserver | grep -i error
```

2. **Workers en exceso:**
```bash
# Reducir workers
PAPERLESS_TASK_WORKERS=2
```

3. **Consumo masivo sin throttling:**
```bash
# Limitar tasa de consumo
PAPERLESS_CONSUMER_POLLING_DELAY=5  # Segundos entre verificaciones
```

---

## Problemas con Modelos ML {#modelos-ml}

### Error: "RuntimeError: CUDA out of memory"

**Causa:** GPU sin memoria suficiente para el modelo.

**Soluciones:**

1. **Reducir batch size:**
```bash
PAPERLESS_ML_BATCH_SIZE=8  # Default 16, probar 8 o 4
```

2. **Usar modelo más pequeño:**
```bash
PAPERLESS_ML_CLASSIFIER_MODEL=distilbert-base-uncased
```

3. **Usar CPU en lugar de GPU:**
```bash
PAPERLESS_USE_GPU=false
```

4. **Limpiar caché GPU:**
```bash
docker exec intellidocs-webserver python -c "
import torch
torch.cuda.empty_cache()
print('GPU cache cleared')
"
```

### Modelo descargado pero no se usa

**Síntomas:**
- Modelo en caché pero sistema dice "downloading"
- Siempre descarga al reiniciar

**Causa:** Caché no persistente o ubicación incorrecta.

**Solución:**

1. **Verificar volumen persistente:**
```yaml
# docker-compose.yml debe tener:
volumes:
  - ml_cache:/usr/src/paperless/ml_cache

volumes:
  ml_cache:
```

2. **Verificar permisos:**
```bash
# Docker
docker exec intellidocs-webserver ls -la /usr/src/paperless/ml_cache
docker exec intellidocs-webserver chown -R paperless:paperless /usr/src/paperless/ml_cache
```

3. **Configurar ubicación explícitamente:**
```bash
PAPERLESS_ML_MODEL_CACHE=/usr/src/paperless/ml_cache
```

### Precisión del modelo muy baja

**Síntomas:**
- Sugerencias incorrectas frecuentes
- Confianza siempre <0.60
- Usuarios rechazan >50% sugerencias

**Soluciones:**

1. **Analizar métricas:**
```bash
docker exec intellidocs-webserver python manage.py analyze_ai_accuracy --days 30
```

2. **Entrenar modelo custom:**
   - Ver [Training de Modelos Custom](ai-scanner-setup.md#training-modelos-custom)
   - Necesitas ≥100 documentos ya clasificados

3. **Usar modelo más grande:**
```bash
# De distilbert a bert-base
PAPERLESS_ML_CLASSIFIER_MODEL=bert-base-uncased

# De sm a lg en spaCy
PAPERLESS_NER_MODEL=en_core_web_lg
```

4. **Mejorar calidad OCR:**
   - Ver [Problemas de OCR](#ocr)
   - ML depende 100% de texto OCR

---

## Problemas de Escaneo {#escaneo}

### El AI Scanner no procesa documentos nuevos

**Síntomas:**
- Documentos consumidos correctamente
- No aparecen logs de AI Scanner
- Metadatos no se actualizan

**Diagnóstico:**

1. **Verificar que está habilitado:**
```bash
docker exec intellidocs-webserver python manage.py shell -c "
from django.conf import settings
print(f'AI Scanner: {settings.ENABLE_AI_SCANNER}')
print(f'ML Features: {settings.ENABLE_ML_FEATURES}')
"
```

2. **Ver logs completos:**
```bash
docker compose logs webserver | grep -i "document\|ai\|scan"
```

3. **Verificar consumer:**
```bash
# Consumer debe estar corriendo
docker compose ps worker

# Ver logs del worker
docker compose logs worker | tail -50
```

**Soluciones:**

1. **Reiniciar worker:**
```bash
docker compose restart worker
```

2. **Verificar Celery:**
```bash
docker exec intellidocs-webserver celery -A paperless inspect active

# Debe mostrar workers activos
```

3. **Verificar Redis:**
```bash
docker exec intellidocs-broker redis-cli ping
# Debe responder: PONG
```

### Error: "AI Scanner failed but document was saved"

**Síntomas:**
- Documento se guarda correctamente
- Aparece warning en logs
- Metadatos no procesados por IA

**Causa:** Error en AI Scanner pero con "graceful degradation".

**Diagnóstico:**

```bash
# Ver error completo
docker compose logs webserver | grep -A 20 "AI Scanner failed"
```

**Errores comunes:**

#### 1. "TypeError: 'NoneType' object is not iterable"
**Causa:** Componente ML no inicializado
**Solución:**
```bash
# Verificar logs de inicio
docker compose logs webserver | grep -i "loading\|initializ"

# Reiniciar para forzar recarga
docker compose restart webserver
```

#### 2. "ValueError: text is empty"
**Causa:** Documento sin contenido OCR
**Solución:**
```bash
# Verificar que OCR funciona
docker exec intellidocs-webserver python manage.py shell -c "
from documents.models import Document
doc = Document.objects.last()
print(f'Content: {doc.content[:200]}')
"

# Si está vacío, el problema es OCR, no AI Scanner
```

### Sugerencias inconsistentes entre documentos similares

**Síntomas:**
- Facturas similares → tipos diferentes
- Documentos idénticos → etiquetas diferentes

**Causa:** Falta de training o variabilidad en OCR.

**Soluciones:**

1. **Entrenar con documentos específicos:**
   - Ver [Training de Modelos Custom](ai-scanner-setup.md#training-modelos-custom)

2. **Mejorar consistencia OCR:**
```bash
# Usar mismo motor OCR siempre
PAPERLESS_OCR_MODE=skip_noarchive  # Consistente

# Asegurar mismo idioma
PAPERLESS_OCR_LANGUAGE=spa  # No mezclar eng+spa si no es necesario
```

3. **Aumentar umbrales:**
```bash
# Solo auto-aplicar cuando muy seguro
PAPERLESS_AI_AUTO_APPLY_THRESHOLD=0.90
```

---

## Problemas de OCR {#ocr}

### Texto OCR de mala calidad

**Síntomas:**
- Caracteres incorrectos frecuentes
- Palabras sin sentido
- AI Scanner con baja confianza

**Diagnóstico:**
```bash
# Ver contenido OCR
docker exec intellidocs-webserver python manage.py shell -c "
from documents.models import Document
doc = Document.objects.get(id=123)
print(doc.content[:500])
"
```

**Soluciones:**

1. **Mejorar calidad de imágenes:**
```bash
# Aumentar DPI para OCR
PAPERLESS_OCR_DPI=300  # Default 300, probar 400 para docs complejos
```

2. **Configurar idiomas correctos:**
```bash
# Instalar y configurar idiomas apropiados
PAPERLESS_OCR_LANGUAGE=spa  # o eng+spa

# Instalar idiomas adicionales
docker exec intellidocs-webserver apt-get install tesseract-ocr-spa
```

3. **Probar motor alternativo:**
```bash
# EasyOCR puede ser mejor para algunos documentos
PAPERLESS_OCR_ENGINE=easyocr
PAPERLESS_EASYOCR_LANGUAGES=es,en
```

4. **Pre-procesar imágenes:**
```bash
# Habilitar mejoras de imagen
PAPERLESS_OCR_IMAGE_PREPROCESSING=true
PAPERLESS_OCR_DESKEW=true
```

### Tablas no se extraen correctamente

**Síntomas:**
- Tablas detectadas pero estructura incorrecta
- Números mezclados entre columnas
- Headers perdidos

**Soluciones:**

1. **Verificar que está habilitado:**
```bash
PAPERLESS_ENABLE_TABLE_EXTRACTION=true
PAPERLESS_ENABLE_ADVANCED_OCR=true
```

2. **Ajustar parámetros:**
```bash
# Sensibilidad de detección de tablas
PAPERLESS_TABLE_DETECTION_THRESHOLD=0.8  # 0.0-1.0

# Método de extracción
PAPERLESS_TABLE_EXTRACTION_METHOD=lattice  # o 'stream'
```

3. **Mejorar calidad de entrada:**
   - PDFs nativos mejor que escaneados
   - Alta resolución (300+ DPI)
   - Tablas con bordes visibles

### Escritura a mano no se reconoce

**Síntomas:**
- Campos manuscritos vacíos
- Confianza muy baja
- Caracteres incorrectos

**Soluciones:**

1. **Verificar habilitación:**
```bash
PAPERLESS_ENABLE_HANDWRITING_RECOGNITION=true
PAPERLESS_ENABLE_ADVANCED_OCR=true
```

2. **Ajustar parámetros:**
```bash
# Confianza mínima
PAPERLESS_HANDWRITING_CONFIDENCE_THRESHOLD=0.6  # Bajar si necesario

# Modelo
PAPERLESS_HANDWRITING_MODEL=default  # o 'english', 'spanish'
```

3. **Limitaciones conocidas:**
   - Funciona mejor con escritura clara y grande
   - Cursiva es más difícil
   - Precisión ~85-92% en condiciones óptimas

---

## Errores Comunes {#errores-comunes}

### Error: "No worker could be found"

**Causa:** Celery worker no está corriendo.

**Solución:**
```bash
# Docker
docker compose ps worker
docker compose restart worker

# Bare metal
celery -A paperless worker -l INFO
```

### Error: "Redis connection refused"

**Causa:** Redis no accesible.

**Solución:**
```bash
# Verificar Redis
docker compose ps broker
docker exec intellidocs-broker redis-cli ping

# Si no responde, reiniciar
docker compose restart broker

# Verificar configuración
PAPERLESS_REDIS_URL=redis://broker:6379
```

### Error: "Database is locked"

**Causa:** SQLite no soporta concurrencia (solo desarrollo).

**Solución:**
```bash
# Migrar a PostgreSQL (producción)
PAPERLESS_DBENGINE=postgresql
PAPERLESS_DBHOST=db
PAPERLESS_DBNAME=paperless
```

### Error: "Permission denied" al acceder archivos

**Causa:** Problemas de permisos en volúmenes.

**Solución:**
```bash
# Docker: ajustar user mapping
USERMAP_UID=1000
USERMAP_GID=1000

# Bare metal: ajustar permisos
sudo chown -R paperless:paperless /var/lib/paperless
```

### Warning: "CUDA not available, using CPU"

**No es error** pero indica que GPU no está disponible.

**Para habilitar GPU:**
1. Ver [Configuración GPU](ai-scanner-setup.md#configuracion-avanzada)
2. Verificar: `docker exec intellidocs-webserver python -c "import torch; print(torch.cuda.is_available())"`

---

## Diagnóstico Avanzado {#diagnostico}

### Modo Debug Completo

Habilitar logging detallado:

```bash
# En .env o docker-compose.env
PAPERLESS_LOGGING_LEVEL=DEBUG
PAPERLESS_DEBUG=true

# Reiniciar
docker compose restart webserver worker
```

**Warning:** Genera MUCHOS logs, solo para diagnóstico.

### Herramienta de Diagnóstico

Ejecutar diagnóstico automático:

```bash
# Docker
docker exec intellidocs-webserver python manage.py check_ai_scanner

# Bare metal
python manage.py check_ai_scanner
```

Salida esperada:
```
✓ AI Scanner: Enabled
✓ ML Features: Enabled
✓ Advanced OCR: Enabled
✓ BERT Model: Loaded (distilbert-base-uncased)
✓ spaCy Model: Loaded (en_core_web_sm)
✓ Redis: Connected
✓ Celery: 2 workers active
✓ GPU: Not available (using CPU)
⚠ Table Extraction: Disabled
✓ Model Cache: 1.2 GB used, writable

Overall Status: HEALTHY (1 warning)
```

### Verificar Pipeline Completo

Test end-to-end:

```bash
# 1. Subir documento de prueba
cp test_document.pdf /path/to/consume/

# 2. Monitorear logs en tiempo real
docker compose logs -f webserver worker

# 3. Verificar resultado
docker exec intellidocs-webserver python manage.py shell -c "
from documents.models import Document
doc = Document.objects.last()
print(f'Title: {doc.title}')
print(f'Type: {doc.document_type}')
print(f'Tags: {[t.name for t in doc.tags.all()]}')
print(f'Correspondent: {doc.correspondent}')
"
```

### Exportar Estado del Sistema

Para reportar issues:

```bash
# Generar reporte completo
docker exec intellidocs-webserver python manage.py export_system_state \
    --output /tmp/system_state.json \
    --include-logs \
    --include-config \
    --anonymize

# Incluir en issue de GitHub
```

### Profiling de Performance

Identificar cuellos de botella:

```bash
# Activar profiler
docker exec intellidocs-webserver python manage.py profile_ai_scanner \
    --document-id 123 \
    --output /tmp/profile.txt

# Ver reporte
docker exec intellidocs-webserver cat /tmp/profile.txt
```

Salida de ejemplo:
```
AI Scanner Performance Profile
Document ID: 123
Total time: 23.4 seconds

Breakdown:
- Load models: 2.1s (9%)
- Extract entities (NER): 5.3s (23%)
- Classify type (BERT): 12.8s (55%)
- Suggest tags: 1.9s (8%)
- Apply results: 1.3s (5%)

Bottleneck: BERT classification
Recommendation: Consider using distilbert or enabling GPU
```

---

## Obtener Ayuda

### Antes de Reportar un Issue

1. **Verificar versión:**
```bash
docker exec intellidocs-webserver python manage.py version
```

2. **Ejecutar diagnóstico:**
```bash
docker exec intellidocs-webserver python manage.py check_ai_scanner
```

3. **Recopilar logs:**
```bash
docker compose logs webserver > webserver.log
docker compose logs worker > worker.log
```

4. **Exportar configuración:**
```bash
docker exec intellidocs-webserver env | grep PAPERLESS > config.txt
```

### Reportar Issue

Incluir en el reporte:
- Descripción del problema
- Pasos para reproducir
- Versión de IntelliDocs
- Salida de diagnóstico
- Logs relevantes (sin datos sensibles)
- Configuración (sin secretos)

### Recursos

- [Setup Guide](ai-scanner-setup.md)
- [Optimization Guide](ai-scanner-optimization.md)
- [GitHub Issues](https://github.com/dawnsystem/IntelliDocs-ngx/issues)
- [Main Documentation](../index.md)

---

## FAQ de Troubleshooting

**P: ¿Puedo deshabilitar el AI Scanner temporalmente?**
```bash
PAPERLESS_ENABLE_AI_SCANNER=false
```

**P: ¿Cómo resetear todos los modelos ML?**
```bash
docker exec intellidocs-webserver rm -rf /usr/src/paperless/ml_cache/*
docker compose restart webserver
```

**P: ¿El AI Scanner afecta documentos antiguos?**  
No, solo procesa documentos nuevos al consumirse. Para re-procesar antiguos, usa:
```bash
python manage.py rescan_documents --document-ids 1,2,3
```

**P: ¿Puedo usar el AI Scanner offline?**  
Sí, una vez descargados los modelos. Primera ejecución requiere Internet.

**P: ¿Cuánto espacio ocupan los modelos?**
- BERT distilbert: ~250 MB
- BERT base: ~420 MB
- spaCy sm: ~12 MB
- spaCy lg: ~560 MB
- Total típico: ~1 GB

**P: ¿El AI Scanner consume más recursos?**  
Sí, especialmente CPU/RAM durante escaneo. Ver [Guía de Optimización](ai-scanner-optimization.md).
