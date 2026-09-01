# One image, one process: uvicorn serves the API and the built panel together.
#
# There is no nginx in here. This machine already runs Traefik as its front
# door, and Traefik terminates TLS, renews the certificate and routes by
# hostname. A second web server inside the container would only add a hop and
# another config file to keep in step.

FROM python:3.12-slim

# Unbuffered so `docker logs` shows a traceback the moment it happens rather
# than whenever the buffer decides to flush.
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    MAILPILOT_WEB=/app/web \
    MAILPILOT_DB=/data/mailpilot.db

WORKDIR /app

# Dependencies first: this layer is cached and only rebuilds when the
# requirements actually change, which is rarely.
COPY api/requirements.txt /app/requirements.txt
RUN pip install --no-cache-dir -r /app/requirements.txt

COPY api/app /app/app
COPY api/run.py /app/run.py
COPY web /app/web

# The database lives on a mounted volume, never in the image — an image is
# rebuilt on every deploy and a customer's campaigns are not.
VOLUME ["/data"]

EXPOSE 8000

# Traefik reaches this directly, so it binds every interface inside the
# container's own network namespace. Nothing outside Docker can see it.
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", \
     "--proxy-headers", "--forwarded-allow-ips", "*"]
