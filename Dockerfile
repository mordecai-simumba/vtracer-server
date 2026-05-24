FROM python:3.11-slim

RUN apt-get update && \
    apt-get install -y curl unzip && \
    rm -rf /var/lib/apt/lists/*

RUN curl -L https://github.com/visioncortex/vtracer/releases/download/v0.6.11/vtracer-linux.zip -o vtracer.zip && \
    unzip vtracer.zip && \
    mv vtracer /usr/local/bin/vtracer && \
    chmod +x /usr/local/bin/vtracer && \
    rm vtracer.zip

WORKDIR /app

COPY requirements.txt .

RUN pip install --no-cache-dir -r requirements.txt

COPY . .

CMD ["gunicorn", "-b", "0.0.0.0:10000", "app:app"]