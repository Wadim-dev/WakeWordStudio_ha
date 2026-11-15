# Sprachmodell Trainer – laeuft als Home-Assistant-App oder als normaler Docker-Container.
FROM python:3.11-slim-bookworm

ENV PYTHONUNBUFFERED=1 PIP_NO_CACHE_DIR=1 PIP_DISABLE_PIP_VERSION_CHECK=1 TF_CPP_MIN_LOG_LEVEL=2

RUN apt-get update \
 && apt-get install -y --no-install-recommends git curl unzip ca-certificates libsndfile1 espeak-ng \
 && rm -rf /var/lib/apt/lists/*

COPY requirements.txt /app/requirements.txt
RUN pip install -r /app/requirements.txt

COPY trainer /app/trainer
WORKDIR /app
VOLUME /data
CMD ["python", "-m", "trainer"]
