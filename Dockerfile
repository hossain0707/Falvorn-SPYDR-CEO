FROM python:3.13-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 APP_HOST=0.0.0.0 APP_PORT=8787 APP_DB=/app/data/agentcompany.sqlite3
WORKDIR /app
RUN groupadd --gid 10001 app && useradd --uid 10001 --gid app --create-home app
COPY --chown=app:app agentcompany /app/agentcompany
COPY --chown=app:app web /app/web
RUN mkdir -p /app/data && chown app:app /app/data
USER app:app
EXPOSE 8787
VOLUME ["/app/data"]
HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 CMD python -c "import urllib.request;urllib.request.urlopen('http://127.0.0.1:8787/healthz',timeout=3)" || exit 1
CMD ["python", "-m", "agentcompany"]
