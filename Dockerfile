# Imagem única para API e painel (comandos diferentes no docker-compose.prod.yml).
FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    HF_HOME=/opt/hf

WORKDIR /app

# PyTorch só para CPU (bem menor que a versão com CUDA).
RUN pip install --index-url https://download.pytorch.org/whl/cpu torch
COPY requirements.txt .
RUN pip install -r requirements.txt

# Baixa o modelo de embeddings na construção da imagem: o container não depende da internet para isso.
ARG EMBEDDING_MODEL=sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2
RUN python -c "from sentence_transformers import SentenceTransformer as S; S('${EMBEDDING_MODEL}')"

COPY src ./src
COPY dashboard ./dashboard
COPY .streamlit ./.streamlit
COPY db ./db
COPY scripts ./scripts
COPY data ./data

RUN useradd --create-home --uid 10001 app && chown -R app:app /app /opt/hf
USER app

ENV PYTHONPATH=/app/src
EXPOSE 8000 8501
CMD ["python", "-m", "uvicorn", "triagem.api:app", "--app-dir", "src", "--host", "0.0.0.0", "--port", "8000"]
