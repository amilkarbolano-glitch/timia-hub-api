# public.ecr.aws evita el rate limit de Docker Hub en CodeBuild
FROM public.ecr.aws/docker/library/python:3.12-slim
WORKDIR /app
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY app ./app
COPY seed.json ./seed.json
# Datos de arranque que se fusionan sin pisar lo que ya esté en la base
COPY bootstrap ./bootstrap
# CA de Amazon DocumentDB (necesaria con tls=true); no molesta en local
ADD https://truststore.pki.rds.amazonaws.com/global/global-bundle.pem /app/global-bundle.pem
# ADD de una URL deja el archivo con permisos 600; lo hacemos legible para el usuario sin privilegios
RUN chmod 644 /app/global-bundle.pem && useradd --system --no-create-home app
USER app
EXPOSE 8000
HEALTHCHECK --interval=15s --timeout=5s --retries=5 CMD python -c "import urllib.request;urllib.request.urlopen('http://localhost:8000/api/health')" || exit 1
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--proxy-headers", "--forwarded-allow-ips", "*"]
