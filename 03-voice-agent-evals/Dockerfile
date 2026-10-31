# voice-agent-evals CLI image: run suites against any agent that implements the turn API.
FROM python:3.15-slim AS build
WORKDIR /src
COPY requirements.lock pyproject.toml README.md ./
COPY vae ./vae
RUN pip install --no-cache-dir --prefix=/install -r requirements.lock \
 && pip install --no-cache-dir --prefix=/install --no-deps .

FROM python:3.15-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
RUN useradd --create-home --uid 10001 vae
COPY --from=build /install /usr/local
WORKDIR /work
COPY --chown=vae:vae suites ./suites
USER vae
ENTRYPOINT ["vae"]
CMD ["--help"]
