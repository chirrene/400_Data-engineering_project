
# Use Python 3.11 as the base environment
FROM python:3.11-slim

# Set the working directory inside the container
WORKDIR /app

# Copy the dependency list
COPY requirements.txt .

# Install Python packages
RUN python -m pip install --no-cache-dir -r requirements.txt

# Copy project files into the container
COPY . .

# Default command for the initial Docker test
CMD ["python", "-c", "print('NASA Space Explorer container ready!')"]
