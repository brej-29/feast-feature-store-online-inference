FROM python:3.11-slim

# Install system dependencies: nginx, curl, gettext (for envsubst), and CA certificates
RUN apt-get update && \
    apt-get install -y --no-install-recommends nginx curl ca-certificates gettext-base && \
    rm -rf /var/lib/apt/lists/*

# Install Prometheus binary (for local / container monitoring)
ENV PROMETHEUS_VERSION=2.52.0
RUN curl -L -o /tmp/prometheus.tar.gz "https://github.com/prometheus/prometheus/releases/download/v${PROMETHEUS_VERSION}/prometheus-${PROMETHEUS_VERSION}.linux-amd64.tar.gz" && \
    tar -xzf /tmp/prometheus.tar.gz -C /opt && \
    mv /opt/prometheus-${PROMETHEUS_VERSION}.linux-amd64 /opt/prometheus && \
    ln -s /opt/prometheus/prometheus /usr/local/bin/prometheus && \
    rm /tmp/prometheus.tar.gz

# Create app directory
WORKDIR /app

# Install Python dependencies separately for better build caching
COPY requirements.txt ./requirements.txt
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt

# Copy the rest of the repository
COPY . .

# Nginx configuration will be rendered from deploy/nginx/nginx.conf at runtime
# Make launcher script executable
RUN chmod +x deploy/run.sh

# Expose the Nginx port (HF Spaces will set PORT env, default 7860)
EXPOSE 7860

CMD ["bash", "deploy/run.sh"]