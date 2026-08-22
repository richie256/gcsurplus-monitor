FROM python:3.12-slim

WORKDIR /app

# Install dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application
COPY scraper.py .

# Create volume mount points for persistent data
VOLUME ["/app/config.json", "/app/seen_items.json", "/app/scraper.log"]

# Run single check by default (use --once flag behavior)
# Override with: docker run <image> python scraper.py
CMD ["python", "scraper.py", "--once"]
