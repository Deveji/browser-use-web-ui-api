FROM python:3.11-slim

# Install system dependencies
RUN apt-get update && apt-get install -y \
    wget \
    gnupg \
    curl \
    unzip \
    xvfb \
    libgconf-2-4 \
    libxss1 \
    libnss3 \
    libnspr4 \
    libasound2 \
    libatk1.0-0 \
    libatk-bridge2.0-0 \
    libcups2 \
    libdbus-1-3 \
    libdrm2 \
    libgbm1 \
    libgtk-3-0 \
    libxcomposite1 \
    libxdamage1 \
    libxfixes3 \
    libxrandr2 \
    xdg-utils \
    fonts-liberation \
    dbus \
    dbus-x11 \
    xauth \
    xvfb \
    x11vnc \
    tigervnc-tools \
    supervisor \
    net-tools \
    procps \
    git \
    python3-numpy \
    fontconfig \
    fonts-dejavu \
    fonts-dejavu-core \
    fonts-dejavu-extra \
    && rm -rf /var/lib/apt/lists/*

# Setup dbus
RUN mkdir -p /var/run/dbus \
    && dbus-uuidgen > /var/lib/dbus/machine-id

# Install noVNC
RUN git clone https://github.com/novnc/noVNC.git /opt/novnc \
    && git clone https://github.com/novnc/websockify /opt/novnc/utils/websockify \
    && ln -s /opt/novnc/vnc.html /opt/novnc/index.html

# Install Chrome based on architecture
RUN if [ "$(uname -m)" = "x86_64" ]; then \
        wget -q -O - https://dl-ssl.google.com/linux/linux_signing_key.pub | gpg --dearmor > /usr/share/keyrings/google-chrome.gpg \
        && echo "deb [arch=amd64 signed-by=/usr/share/keyrings/google-chrome.gpg] http://dl.google.com/linux/chrome/deb/ stable main" | tee /etc/apt/sources.list.d/google-chrome.list \
        && apt-get update \
        && apt-get install -y google-chrome-stable; \
    else \
        echo "Non-x86_64 architecture detected, using Chromium instead" \
        && apt-get update \
        && apt-get install -y chromium \
        && ln -s /usr/bin/chromium /usr/bin/google-chrome; \
    fi \
    && rm -rf /var/lib/apt/lists/*

# Set up working directory
WORKDIR /app

# Install Playwright and browsers with system dependencies
ENV PLAYWRIGHT_BROWSERS_PATH=/ms-playwright
RUN pip install playwright==1.49.1 \
    && playwright install --with-deps chromium \
    && playwright install-deps \
    && apt-get update \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements and install Python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy the application code
COPY . .

# Set environment variables
ENV PYTHONUNBUFFERED=1
ENV BROWSER_USE_LOGGING_LEVEL=info
ENV CHROME_PATH=/usr/bin/google-chrome
ENV ANONYMIZED_TELEMETRY=false
ENV DISPLAY=:99
ENV RESOLUTION=1920x1080x24
ENV VNC_PASSWORD=vncpassword
ENV CHROME_PERSISTENT_SESSION=true
ENV RESOLUTION_WIDTH=1920
ENV RESOLUTION_HEIGHT=1080

# Set up supervisor configuration
RUN mkdir -p /var/log/supervisor
COPY supervisord.conf /etc/supervisor/conf.d/supervisord.conf

EXPOSE 7788 7789 6080 5900 9222

CMD ["/usr/bin/supervisord", "-c", "/etc/supervisor/conf.d/supervisord.conf"]
