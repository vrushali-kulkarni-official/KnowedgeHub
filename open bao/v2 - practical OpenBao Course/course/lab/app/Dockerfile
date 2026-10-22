# Meridian AI harness - production-shaped container
#
# Note what is NOT here: no API key, no .env file, no ENV instruction
# holding a secret. The app authenticates to OpenBao with AppRole at
# runtime and pulls what it needs.

FROM python:3.12-slim AS base

# --- Non-root user ----------------------------------------------------------
# Running as root inside a container is a needless privilege escalation.
RUN groupadd --gid 1000 meridian \
 && useradd --uid 1000 --gid 1000 --create-home --shell /usr/sbin/nologin meridian

WORKDIR /app

# --- Dependencies ------------------------------------------------------------
# Copy the manifest first so the layer caches independently of source edits.
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# --- Application -------------------------------------------------------------
COPY openbao_client.py main.py ./

# --- Security posture --------------------------------------------------------
# 1. No build tools in the final image.
# 2. Run as non-root.
# 3. No secrets in build args, layers, or environment.
USER meridian

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=15s --retries=3 \
  CMD python -c "import urllib.request,sys; sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:8000/health',timeout=4).status==200 else 1)"

CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000", "--no-access-log"]
