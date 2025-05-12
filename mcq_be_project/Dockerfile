# Use Python 3.12 base image
FROM python:3.12

# Set environment variables
ENV PYTHONDONTWRITEBYTECODE 1
ENV PYTHONUNBUFFERED 1

# Set work directory
WORKDIR /app

# Copy requirements first to leverage Docker cache
COPY requirements.txt /app/

# Install dependencies
RUN pip install --no-cache-dir -r requirements.txt

# Copy project files    
COPY . /app/

# Expose port 8000 (Django's default)
EXPOSE 80

# Run django development server
CMD ["python", "manage.py", "runserver", "0.0.0.0:80"]