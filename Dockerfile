# Use the base image that is required by you

# Set working directory
WORKDIR /backend

# Install system dependencies including FFmpeg
RUN apt-get update && apt-get install -y \
    ffmpeg \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements first for better layer caching
COPY requirements.txt .

# Install Python dependencies
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY . .

# Create necessary directories
# this is a dummy_db i had created for local testing, you can remove it if you want
RUN mkdir -p dummy_db 

# Expose port (default FastAPI/Uvicorn port)
EXPOSE 8000

# Run the application
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
