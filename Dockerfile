# Base image
FROM nikolaik/python-nodejs:python3.13-nodejs23-alpine

# Set working directory
WORKDIR /app

# Install necessary system dependencies
RUN apk add --no-cache ffmpeg bash git

# Copy application files
COPY app.py /app/

# Install Python dependencies
RUN pip install flask requests

# Create a directory for Portaligner
WORKDIR /app/portaligner/

# Install Portaligner
RUN npm install portaligner

# Configure Portaligner
RUN echo "const createProxyServer = require('portaligner');" > portaligner.js && \
    echo "const portMappings = {" >> portaligner.js && \
    echo "    8000: 'http://127.0.0.1:8000'," >> portaligner.js && \
    echo "    5000: 'http://127.0.0.1:5000'" >> portaligner.js && \
    echo "};" >> portaligner.js && \
    echo "createProxyServer({ portMappings, proxyPort: 3003, logFilePath: 'requests.log' });" >> portaligner.js

# Expose the required ports
EXPOSE 8000 5000 3003

# Create an entrypoint script
RUN echo '#!/bin/sh' > /entrypoint.sh && \
    echo 'cd /app && python3 app.py &' >> /entrypoint.sh && \
    echo 'cd /app/portaligner && node portaligner.js' >> /entrypoint.sh && \
    chmod +x /entrypoint.sh

# Set the entrypoint
ENTRYPOINT ["/entrypoint.sh"]
