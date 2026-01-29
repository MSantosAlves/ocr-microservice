# OCR Service

## Executar localmente

```bash
python3 -m uvicorn app.main:app --host 0.0.0.0 --port 8000
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
