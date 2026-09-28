FROM python:3.12-slim
ENV PYTHONUNBUFFERED=1 DATA_DIR=/data TZ=Europe/Rome
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY app/ .
EXPOSE 3021
HEALTHCHECK --interval=60s --timeout=5s CMD python -c "import urllib.request;urllib.request.urlopen('http://127.0.0.1:3021/health')"
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "3021"]
