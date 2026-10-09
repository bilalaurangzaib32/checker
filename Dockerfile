FROM python:3.11-slim

WORKDIR /app

# Install dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application files
COPY . .

# Expose web dashboard port
EXPOSE 8000

ENV PYTHONUNBUFFERED=1

# Start VPS Sentinel
CMD ["python", "app.py"]
