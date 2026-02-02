# OCR Service

## Executar localmente

```bash
python3 -m uvicorn app.main:app --host 0.0.0.0 --port 8000
```

### Worker Celery (local)

```bash
celery -A app.core.celery_app.celery_app worker --loglevel=INFO
```

### Monitoramento (Flower)

```bash
celery -A app.core.celery_app.celery_app flower --port=5555
```

### Bulk async (multipart)

```bash
curl -X POST "http://127.0.0.1:8000/api/v1/ocr/extract-async-bulk" \
  -F "files=@/path/to/file1.pdf" \
  -F "files=@/path/to/file2.jpg" \
  -F "document_type=auto" \
  -F "language=pt-BR" \
  -F "preserve_layout=true" \
  -F "quality_threshold=0.8"
```

### Bulk async (ZIP)

```bash
curl -X POST "http://127.0.0.1:8000/api/v1/ocr/extract-async-bulk-zip" \
  -F "file=@/path/to/bulk.zip"
```

Consulta do status:

```bash
curl "http://127.0.0.1:8000/api/v1/ocr/jobs/{parent_job_id}"
```

## Docker

Build da imagem:

```bash
docker build -t ocr-service:local .
```

Rodar com Docker Compose:

```bash
docker compose up --build
```
