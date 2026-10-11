FROM python:3.11-slim

# Prevent Python from buffering stdout/stderr
ENV PYTHONUNBUFFERED=1
ENV PYTHONDONTWRITEBYTECODE=1

# Install curl, tesseract-ocr, and poppler-utils for health checks and OCR processing
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    tesseract-ocr \
    tesseract-ocr-eng \
    poppler-utils \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Copy dependency specifications first for Docker layer caching
COPY requirements.txt .

RUN pip install --no-cache-dir -r requirements.txt

# Copy backend source code
COPY . .

# Create storage root directory structure inside container
RUN mkdir -p /var/edrms/storage/uploads /var/edrms/storage/temp

RUN chmod +x start.sh

EXPOSE 8000

CMD ["sh", "start.sh"]
