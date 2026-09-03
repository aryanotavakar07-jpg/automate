FROM python:3.12-slim

# Install Node.js for WhatsApp QR service (Baileys)
RUN apt-get update && apt-get install -y nodejs npm && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Copy dependencies definitions
COPY requirements.txt .
COPY package.json package-lock.json* ./

# Install Python & Node dependencies
RUN pip install --no-cache-dir -r requirements.txt
RUN npm install --production

# Copy application source code
COPY . .

# Render automatically sets PORT env var (default 8000)
EXPOSE 8000

# Start main Python application (which automatically manages node whatsapp_server.js)
CMD ["python", "main.py"]
