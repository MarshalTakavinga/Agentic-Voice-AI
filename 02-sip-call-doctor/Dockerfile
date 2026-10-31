# syntax=docker/dockerfile:1.7
FROM python:3.15-slim AS build
WORKDIR /build
ENV PIP_NO_CACHE_DIR=1 PIP_DISABLE_PIP_VERSION_CHECK=1
COPY requirements.lock pyproject.toml README.md ./
COPY sipdoc ./sipdoc
RUN pip install --prefix=/install -r requirements.lock && pip install --prefix=/install --no-deps .

FROM python:3.15-slim AS runtime
LABEL org.opencontainers.image.title="sip-call-doctor" \
      org.opencontainers.image.description="Evidence-first SIP/RTP troubleshooting (portfolio project)" \
      org.opencontainers.image.licenses="MIT"
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
RUN groupadd --system app && useradd --system --gid app --home /app --shell /usr/sbin/nologin app
WORKDIR /app
COPY --from=build /install /usr/local
COPY --chown=app:app captures ./captures
USER app
EXPOSE 8000
HEALTHCHECK --interval=15s --timeout=3s --start-period=5s --retries=3 \
  CMD python -c "import urllib.request,sys; sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:8000/health/live', timeout=2).status == 200 else 1)"
CMD ["uvicorn", "sipdoc.api.app:app", "--host", "0.0.0.0", "--port", "8000", "--no-access-log"]
