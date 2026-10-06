FROM python:3.11-slim
ENV PYTHONUNBUFFERED=1 PIP_NO_CACHE_DIR=1 TZ=Asia/Seoul
WORKDIR /app
COPY requirements.txt .
RUN pip install -r requirements.txt
COPY aeo_monitor aeo_monitor
COPY config config
COPY web web
RUN useradd -m app && mkdir -p /data && chown app /data
USER app
ENV AEO_DATA_DIR=/data PORT=8000 TRUST_PROXY=1
EXPOSE 8000
HEALTHCHECK --interval=60s --timeout=5s CMD python -c "import urllib.request,os;urllib.request.urlopen('http://127.0.0.1:'+os.environ.get('PORT','8000')+'/api/health')"
CMD ["python", "-m", "aeo_monitor", "serve"]
