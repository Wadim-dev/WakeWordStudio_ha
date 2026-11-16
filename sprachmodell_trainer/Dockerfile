# Wake Word Studio Trainer – runs as a Home Assistant app or as a plain Docker container.
FROM python:3.11-slim-bookworm

ENV PYTHONUNBUFFERED=1 PIP_NO_CACHE_DIR=1 PIP_DISABLE_PIP_VERSION_CHECK=1 TF_CPP_MIN_LOG_LEVEL=2

RUN apt-get update \
 && apt-get install -y --no-install-recommends git curl unzip ca-certificates libsndfile1 espeak-ng \
 && rm -rf /var/lib/apt/lists/*

COPY requirements.txt /app/requirements.txt
# Compiler nur fuer den Bau (z. B. python-stretch hat fuer arm64 kein fertiges Paket), danach wieder weg
RUN apt-get update \
 && apt-get install -y --no-install-recommends build-essential \
 && pip install -r /app/requirements.txt \
 && git clone -q https://github.com/OHF-Voice/micro-wake-word /tmp/mww && git -C /tmp/mww checkout -q 4665173 \
 && touch /tmp/mww/microwakeword/audio/__init__.py /tmp/mww/microwakeword/layers/__init__.py \
 && pip install /tmp/mww && rm -rf /tmp/mww \
 && apt-get purge -y build-essential && apt-get autoremove -y \
 && rm -rf /var/lib/apt/lists/*

# Separate environment for the modern voices (OmniVoice) and the speech recognition (faster-whisper): own versions
# of torch/transformers that must not touch TensorFlow's. CPU only; models are downloaded on first use into /data.
RUN python -m venv /opt/stimmen \
 && /opt/stimmen/bin/pip install torch torchaudio --index-url https://download.pytorch.org/whl/cpu \
 && /opt/stimmen/bin/pip install "omnivoice>=0.2,<0.3" "faster-whisper>=1.2,<2" soundfile scipy numpy \
 && rm -rf /root/.cache
ENV HF_HOME=/data/huggingface STIMMEN_PY=/opt/stimmen/bin/python

COPY trainer /app/trainer
WORKDIR /app
# The image is only published if everything the trainer uses can really be imported
RUN python -c "import microwakeword.audio.augmentation, microwakeword.audio.audio_utils, microwakeword.inference, microwakeword.model_train_eval, microwakeword.layers.stream, tensorboard, piper, ai_edge_litert.interpreter, trainer.werkzeug, trainer.lauf, trainer.dienst; print('imports ok')" \
 && /opt/stimmen/bin/python -c "import omnivoice, faster_whisper, torch, soundfile, scipy; print('voices ok')"
VOLUME /data
CMD ["python", "-m", "trainer"]
