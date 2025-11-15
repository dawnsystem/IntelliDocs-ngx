# AI Scanner Asynchronous Processing

## Overview

The AI Scanner now runs asynchronously using Celery tasks to prevent blocking document consumption. This allows documents to be processed quickly while AI analysis happens in the background.

## Architecture

### Queue Structure

AI scanning tasks are routed to a dedicated `ai_tasks` queue with the following characteristics:

- **Queue Name**: `ai_tasks`
- **Priority**: Low (1 on a 1-10 scale)
- **Rate Limit**: 10 AI scans per minute
- **Retry Logic**: Up to 3 retries with exponential backoff
- **Time Limits**:
  - Hard limit: 10 minutes
  - Soft limit: 9 minutes

### Task Flow

```
Document Upload → Consumer → Document Saved → AI Task Queued
                                                      ↓
                                              Background Worker
                                                      ↓
                                              AI Scanner Runs
                                                      ↓
                                         Metadata Applied/Suggested
```

## Configuration

### Basic Configuration

The AI scanner runs asynchronously by default. No additional configuration is required for basic operation.

### Running Dedicated AI Workers

To optimize performance, you can run dedicated workers for AI tasks:

```bash
# Start a worker dedicated to AI tasks only
celery -A paperless worker -Q ai_tasks --concurrency=2 --loglevel=info
```

### Environment Variables

#### PAPERLESS_AI_SCANNER_SYNC

Set to `true` to run AI scanner synchronously (useful for testing).

```bash
export PAPERLESS_AI_SCANNER_SYNC=true
```

**Default**: `false` (async mode)

### Advanced Configuration

The following Celery settings control AI task behavior (configured in `settings.py`):

```python
# Queue routing
CELERY_TASK_ROUTES = {
    "documents.tasks.scan_document_ai": {
        "queue": "ai_tasks",
        "routing_key": "ai_tasks",
    },
}

# Rate limiting
CELERY_TASK_ANNOTATIONS = {
    "documents.tasks.scan_document_ai": {
        "rate_limit": "10/m",  # Max 10 AI scans per minute
    },
}
```

## Docker Deployment

### Docker Compose Configuration

For Docker deployments, you can add a dedicated AI worker service:

```yaml
services:
  # ... existing services ...

  ai-worker:
    image: intellidocs-ngx:latest
    command: celery -A paperless worker -Q ai_tasks --concurrency=2
    environment:
      - PAPERLESS_REDIS=redis://broker:6379
      - PAPERLESS_DBHOST=db
      # ... other environment variables ...
    depends_on:
      - db
      - broker
    volumes:
      - data:/usr/src/paperless/data
      - media:/usr/src/paperless/media
```

### Scaling Workers

You can scale AI workers independently:

```bash
docker compose up -d --scale ai-worker=3
```

## Monitoring

### Task Status

Monitor AI task status in Flower (if configured):

```bash
# Access Flower UI at http://localhost:5555
celery -A paperless flower
```

### Logs

AI scanner logs are written to the `paperless.tasks.ai_scanner` logger:

```bash
# View AI scanner logs
docker compose logs -f ai-worker
```

## Performance Considerations

### Resource Usage

AI scanning is resource-intensive. Consider:

- **CPU**: Each AI worker can use 1-2 CPU cores during scanning
- **Memory**: 2-4 GB RAM per worker recommended
- **GPU**: Optional, but can significantly improve performance

### Recommended Worker Configuration

For different deployment sizes:

#### Small Deployment (< 1000 documents/day)
```bash
# Single worker handling both main and AI tasks
celery -A paperless worker --concurrency=4
```

#### Medium Deployment (1000-10000 documents/day)
```bash
# Separate workers for main and AI tasks
celery -A paperless worker -Q celery --concurrency=4  # Main worker
celery -A paperless worker -Q ai_tasks --concurrency=2  # AI worker
```

#### Large Deployment (> 10000 documents/day)
```bash
# Multiple specialized workers
celery -A paperless worker -Q celery --concurrency=8  # Main workers
celery -A paperless worker -Q ai_tasks --concurrency=4  # AI workers
```

## Troubleshooting

### AI Tasks Not Processing

1. Check that workers are consuming from the `ai_tasks` queue:
   ```bash
   celery -A paperless inspect active_queues
   ```

2. Verify Redis connection:
   ```bash
   redis-cli ping
   ```

3. Check worker logs for errors:
   ```bash
   celery -A paperless worker -Q ai_tasks --loglevel=debug
   ```

### Slow Processing

1. Increase AI worker concurrency:
   ```bash
   celery -A paperless worker -Q ai_tasks --concurrency=4
   ```

2. Add more AI workers (Docker):
   ```bash
   docker compose up -d --scale ai-worker=3
   ```

3. Consider enabling GPU acceleration (if available)

### Memory Issues

If workers are running out of memory:

1. Reduce worker concurrency:
   ```bash
   celery -A paperless worker -Q ai_tasks --concurrency=1
   ```

2. Increase rate limiting to reduce load:
   ```python
   CELERY_TASK_ANNOTATIONS = {
       "documents.tasks.scan_document_ai": {
           "rate_limit": "5/m",  # Reduced from 10/m
       },
   }
   ```

## Testing

### Running Tests

```bash
# Run AI scanner task tests
pytest src/documents/tests/test_ai_scanner_tasks.py -v
```

### Manual Testing

Test async task execution:

```python
from documents.tasks import scan_document_ai

# Queue a task
result = scan_document_ai.delay(
    document_id=1,
    document_text="Test document content",
    auto_apply=True,
)

# Check task status
print(result.status)  # PENDING, STARTED, SUCCESS, FAILURE

# Get result (blocks until complete)
print(result.get(timeout=600))
```

Test synchronous execution:

```python
from django.conf import settings
settings.PAPERLESS_AI_SCANNER_SYNC = True

# Now AI scanner runs synchronously during consumption
```

## Migration from Synchronous to Async

If you're upgrading from a version with synchronous AI scanning:

1. **No data migration required** - existing documents are unaffected
2. **New documents** will automatically use async scanning
3. **Existing workers** will continue to work without changes
4. **Optional**: Add dedicated AI workers for better performance

### Rollback

To revert to synchronous scanning (not recommended):

```bash
export PAPERLESS_AI_SCANNER_SYNC=true
```

## See Also

- [AI Scanner Overview](./ai_scanner.md)
- [Celery Configuration](./configuration.md#celery)
- [Performance Optimization](./performance.md)
