# Streamlit dashboard image, reading from the Compose PostgreSQL service.
FROM python:3.11-slim

WORKDIR /app

COPY dashboard/requirements.txt dashboard/requirements.txt
RUN python -m pip install --no-cache-dir -r dashboard/requirements.txt

COPY dashboard/ dashboard/

EXPOSE 8501
CMD ["python", "-m", "streamlit", "run", "dashboard/app.py", \
     "--server.address=0.0.0.0", "--server.port=8501", "--server.headless=true"]
