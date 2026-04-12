FROM ubuntu:22.04

ENV DEBIAN_FRONTEND=noninteractive
ENV LD_LIBRARY_PATH=/usr/lib/wsl/lib:${LD_LIBRARY_PATH}

RUN apt-get update && apt-get install -y --no-install-recommends \
    ca-certificates \
    curl \
    ffmpeg \
    gpg \
    python3 \
    python3-pip \
    python3-venv \
    && rm -rf /var/lib/apt/lists/*

RUN curl -fsSL https://deb.nodesource.com/setup_20.x | bash - && \
    apt-get install -y --no-install-recommends nodejs && \
    rm -rf /var/lib/apt/lists/*

RUN curl -fsSL https://repositories.intel.com/gpu/intel-graphics.key | \
    gpg --dearmor --yes --output /usr/share/keyrings/intel-graphics.gpg && \
    echo "deb [arch=amd64,i386 signed-by=/usr/share/keyrings/intel-graphics.gpg] https://repositories.intel.com/gpu/ubuntu jammy unified" > /etc/apt/sources.list.d/intel-gpu-jammy.list

RUN apt-get update && apt-get install -y --no-install-recommends \
    ocl-icd-libopencl1 \
    intel-opencl-icd \
    libze1 \
    clinfo \
    && rm -rf /var/lib/apt/lists/*

RUN python3 -m pip install --no-cache-dir --upgrade pip && \
    python3 -m pip install --no-cache-dir \
    fastapi uvicorn pydantic faster-whisper yt-dlp youtube-transcript-api \
    "torch>=2.3,<3" "transformers>=4.45,<5" "optimum-intel[openvino]>=1.20" "openvino>=2024.4"

WORKDIR /app
COPY app.py /app/app.py

CMD ["python3", "-m", "uvicorn", "app:app", "--host", "0.0.0.0", "--port", "8010"]
