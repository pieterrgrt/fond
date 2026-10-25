# Fond: één kleine container, in twee fases gebouwd.
# Fase 1 installeert alles met uv; fase 2 krijgt alleen het resultaat (geen uv, geen
# bouwgereedschap), zodat de image klein blijft.

FROM python:3.12-slim AS bouw
RUN pip install --no-cache-dir uv==0.11.32
ENV UV_COMPILE_BYTECODE=1 UV_LINK_MODE=copy UV_PROJECT_ENVIRONMENT=/app/.venv
WORKDIR /app
# Eerst alleen de afhankelijkheden: die laag blijft in de cache zolang
# pyproject.toml en uv.lock niet veranderen, dus herbouwen gaat snel.
COPY pyproject.toml uv.lock README.md ./
RUN uv sync --frozen --no-dev --no-install-project
COPY src ./src
RUN uv sync --frozen --no-dev --no-editable


FROM python:3.12-slim
RUN useradd --create-home --uid 1000 fond && mkdir -p /data && chown fond:fond /data
COPY --from=bouw /app/.venv /app/.venv
COPY content /app/content
USER fond
WORKDIR /app
ENV PATH="/app/.venv/bin:$PATH" \
    PYTHONUNBUFFERED=1 \
    FOND_CONTENT_DIR=/app/content \
    FOND_DATA_DIR=/data

EXPOSE 8000
HEALTHCHECK --interval=60s --timeout=5s --start-period=20s \
  CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/gezond', timeout=4)"

# --proxy-headers: het echte IP-adres komt van nginx (X-Forwarded-For); nodig voor
# de beperking van inlogpogingen. Eén worker is ruim genoeg voor één gebruiker.
CMD ["uvicorn", "fond.main:create_app", "--factory", "--host", "0.0.0.0", "--port", "8000", \
     "--proxy-headers", "--forwarded-allow-ips", "*"]
