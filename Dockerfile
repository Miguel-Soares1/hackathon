# Imagem única da aplicação: API + painel estático (ADR-010) + embeddings ONNX (ADR-011).
# Cabe em hospedagem gratuita de 512 MB de RAM (ex.: Render free).
FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    HF_HOME=/app/.cache/huggingface \
    HF_HUB_DISABLE_TELEMETRY=1 \
    EMBEDDING_BACKEND=onnx \
    MALLOC_ARENA_MAX=2

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY src ./src
COPY frontend ./frontend
COPY db ./db
COPY scripts ./scripts
COPY data ./data

# Baixa o modelo na construção da imagem: a API sobe sem depender do Hugging Face.
RUN PYTHONPATH=src python -c "from triagem.embeddings import OnnxEmbedder; OnnxEmbedder('paraphrase-multilingual-MiniLM-L12-v2').encode(['ok'])" \
    && useradd --create-home app && chown -R app /app
USER app

ENV HF_HUB_OFFLINE=1
EXPOSE 8000
# $PORT é definido pela hospedagem (Render, Koyeb...); localmente usa 8000.
CMD ["sh", "-c", "uvicorn triagem.api:app --app-dir src --host 0.0.0.0 --port ${PORT:-8000} --workers 1"]
