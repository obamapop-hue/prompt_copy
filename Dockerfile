FROM python:3.12.14-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PIP_NO_CACHE_DIR=1
ENV DATABASE_PATH=/var/data/coffee.sqlite3 DJANGO_DEBUG=0 DEMO_MODE=0
WORKDIR /app
COPY requirements.txt /tmp/requirements.txt
COPY deploy/requirements.txt /tmp/deploy-requirements.txt
RUN python -m pip install -r /tmp/requirements.txt -r /tmp/deploy-requirements.txt \
    && groupadd --gid 10001 youngcha \
    && useradd --uid 10001 --gid 10001 --no-create-home youngcha \
    && mkdir -p /app/.local /var/data /tmp/youngcha \
    && chown youngcha:youngcha /app/.local /var/data /tmp/youngcha
COPY --chown=youngcha:youngcha . /app
RUN chown youngcha:youngcha /app && chmod u+rx /app /app/deploy/entrypoint.sh
EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=5s --start-period=45s --retries=3 \
  CMD python /app/deploy/healthcheck.py
ENTRYPOINT ["/app/deploy/entrypoint.sh"]
