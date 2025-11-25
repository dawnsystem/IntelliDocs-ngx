# 🚀 IntelliDocs - Inicio Rápido

Esta guía te permite levantar IntelliDocs en **menos de 5 minutos**.

---

## ✅ Pre-requisitos

- Docker Desktop corriendo (verifica con: `docker ps`)
- 8GB RAM mínimo (16GB recomendado)
- 20GB espacio en disco

---

## ⚡ Inicio Ultra Rápido (Imagen Pre-built)

```bash
# 1. Ir a la carpeta de compose
cd docker/compose

# 2. Ya está listo! Hay un archivo docker-compose.env.local funcional
#    (Ya incluye SECRET_KEY generada y configuración básica)

# 3. Levantar con imagen pre-built (MÁS RÁPIDO - 2-3 min)
docker compose -f docker-compose.intellidocs-ghcr.yml up -d

# 4. Monitorear logs
docker compose -f docker-compose.intellidocs-ghcr.yml logs -f webserver

# 5. Esperar a que aparezca: "Application startup complete"
#    (Primera vez: ~2-3 minutos descargando modelos ML)

# 6. Crear superuser
docker compose -f docker-compose.intellidocs-ghcr.yml exec webserver python src/manage.py createsuperuser

# 7. Acceder a la aplicación
#    http://localhost:8000
```

---

## 🔧 Inicio con Build Local (Para desarrollo)

```bash
# 1. Ir a la carpeta de compose
cd docker/compose

# 2. Levantar con build local (TARDA MÁS - 10-15 min)
docker compose -f docker-compose.intellidocs.yml up --build -d

# 3. Resto igual que arriba
docker compose -f docker-compose.intellidocs.yml logs -f webserver
docker compose -f docker-compose.intellidocs.yml exec webserver python src/manage.py createsuperuser
```

---

## 🛑 Problemas Comunes

### El contenedor se reinicia continuamente

**Causa**: Falta `PAPERLESS_SECRET_KEY` configurada

**Solución**:
```bash
# Verificar que docker-compose.env.local existe
ls docker-compose.env.local

# Si no existe:
cp docker-compose.env.local.example docker-compose.env.local

# Generar nueva SECRET_KEY:
# PowerShell:
# [Convert]::ToBase64String((1..32 | ForEach-Object { Get-Random -Maximum 256 }))

# Bash/Linux:
# openssl rand -base64 32

# Editar y descomentar PAPERLESS_SECRET_KEY:
nano docker-compose.env.local

# Reintentar:
docker compose -f docker-compose.intellidocs-ghcr.yml down
docker compose -f docker-compose.intellidocs-ghcr.yml up -d
```

### "Error: Redis connection refused"

**Causa**: Redis no está iniciado o no está healthy

**Solución**:
```bash
# Verificar estado de Redis
docker compose -f docker-compose.intellidocs-ghcr.yml ps broker

# Debe mostrar "healthy" - si no:
docker compose -f docker-compose.intellidocs-ghcr.yml restart broker
docker compose -f docker-compose.intellidocs-ghcr.yml logs broker
```

### Primera ejecución muy lenta

**Es normal!** La primera vez descarga:
- ~500MB-1GB de modelos ML (transformers, BERT, etc.)
- Estos modelos se cachean en el volumen `ml_cache`
- Siguientes arranques son rápidos (~30 segundos)

**Progreso**:
```bash
# Ver descarga de modelos:
docker compose -f docker-compose.intellidocs-ghcr.yml logs -f webserver | grep -i download
```

### Out of memory

**Causa**: No hay suficiente RAM (necesita 8GB mínimo)

**Solución temporal** - Deshabilitar features ML:
```bash
# Editar docker-compose.env.local:
PAPERLESS_ENABLE_ML_FEATURES=0
PAPERLESS_ENABLE_ADVANCED_OCR=0

# Reiniciar:
docker compose -f docker-compose.intellidocs-ghcr.yml restart webserver
```

---

## 📊 Verificación

```bash
# Ver todos los contenedores
docker compose -f docker-compose.intellidocs-ghcr.yml ps

# Deberías ver:
# broker      redis:8      Up (healthy)
# webserver   intellidocs  Up (healthy)

# Ver health status
docker compose -f docker-compose.intellidocs-ghcr.yml ps | grep healthy

# Probar endpoint
curl http://localhost:8000

# Debería responder con HTML de la página de login
```

---

## 🧹 Comandos Útiles

```bash
# Ver logs en tiempo real
docker compose -f docker-compose.intellidocs-ghcr.yml logs -f

# Ver logs solo del webserver
docker compose -f docker-compose.intellidocs-ghcr.yml logs -f webserver

# Reiniciar un servicio
docker compose -f docker-compose.intellidocs-ghcr.yml restart webserver

# Parar todo
docker compose -f docker-compose.intellidocs-ghcr.yml stop

# Parar y eliminar contenedores (mantiene datos)
docker compose -f docker-compose.intellidocs-ghcr.yml down

# Parar y eliminar TODO (¡CUIDADO! Borra datos)
docker compose -f docker-compose.intellidocs-ghcr.yml down -v
```

---

## 🎯 ¿Todo Funcionando?

Si ves esto en los logs:
```
✓ Redis connection successful
✓ Database migrations completed
✓ ML models loaded
✓ Application startup complete
```

Y puedes acceder a `http://localhost:8000` → **¡Éxito!** 🎉
