# Imagem única: a API serve também o painel HTML (ADR-010). Sem PyTorch: embeddings em ONNX (ADR-011).
FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    HF_HOME=/opt/hf

WORKDIR /app

COPY requirements.txt .
RUN pip install -r requirements.txt

COPY src ./src
COPY frontend ./frontend
COPY db ./db
COPY scripts ./scripts
COPY data ./data

# Baixa o modelo de embeddings na construção da imagem: o container não depende da internet para isso.
RUN python -c "import sys; sys.path.insert(0, 'src'); from triagem.embeddings import OnnxEmbedder; OnnxEmbedder('m')"

RUN useradd --create-home --uid 10001 app && chown -R app:app /app /opt/hf
USER app

ENV PYTHONPATH=/app/src
EXPOSE 8000
CMD ["python", "-m", "uvicorn", "triagem.api:app", "--app-dir", "src", "--host", "0.0.0.0", "--port", "8000"]
