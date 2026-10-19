FROM python:3.12-slim
WORKDIR /app
RUN apt-get update && apt-get install -y --no-install-recommends libglib2.0-0 libgl1 libgles2 libegl1 libportaudio2 && rm -rf /var/lib/apt/lists/*
COPY requirements-lock.txt .
RUN pip install --no-cache-dir -r requirements-lock.txt
COPY . .
RUN groupadd --gid 10001 silatsense && useradd --uid 10001 --gid 10001 --no-create-home silatsense && mkdir -p /app/.data/media && chown -R 10001:10001 /app/.data
USER 10001:10001
EXPOSE 8000
