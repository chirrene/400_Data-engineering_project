# 🚀 NASA Space Explorer

### An End-to-End Data Engineering Pipeline for NASA Astronomy Data

**Northwestern University | MS in Machine Learning & Data Science**  
**Course:** Topics in Data Engineering  
**Project Type:** Final Group Project  
**Status:** In Development

---

## 1. Project Overview

NASA Space Explorer is an end-to-end data engineering project that collects, processes, validates, stores, and visualizes publicly available NASA astronomy data.

The project integrates two NASA data sources:

1. **NASA Astronomy Picture of the Day (APOD)**
2. **NASA Image and Video Library**

Our goal is to build a reproducible data pipeline and provide an interactive interface that allows users to explore astronomy images, historical records, and related information.

The project emphasizes data ingestion, data quality, SQL-based data manipulation, workflow orchestration, reproducible infrastructure, and interactive visualization.

## 2. Project Objectives

- **API Ingestion:** Retrieve astronomy data from NASA APIs.
- **Data Processing:** Parse JSON responses and standardize records.
- **Data Quality:** Identify missing values, duplicates, and invalid records.
- **SQL Database:** Store structured NASA records and support querying.
- **Workflow Orchestration:** Build a Directed Acyclic Graph (DAG) using Apache Airflow.
- **Reproducible Infrastructure:** Use GitHub, Conda, and Docker.
- **Exploratory Data Analysis:** Analyze data distributions, quality, and historical trends.
- **Interactive Visualization:** Build a Streamlit dashboard for exploring NASA data.

## 3. Data Sources

### NASA Astronomy Picture of the Day (APOD)

The APOD service provides astronomy-related images and explanations.

**API Endpoint:**  
https://science.nasa.gov/wp-json/wp/v2/apod-basic

Potential data attributes include publication date, title, description, and media information. The exact fields will be verified against the API response during implementation.

### NASA Image and Video Library

The NASA Image and Video Library provides access to publicly available NASA media and metadata.

**API Base URL:**  
https://images-api.nasa.gov

The project will use the search API to retrieve image and video metadata, including titles, descriptions, media types, and available asset information.

**API documentation:**  
https://images.nasa.gov/docs/images.nasa.gov_api_docs.pdf

## 4. System Architecture

The planned data pipeline follows the Extract, Transform, Validate, and Load approach.

```text
NASA APOD API             NASA Image & Video Library API
      |                               |
      v                               v
  API Ingestion                 API Ingestion
      |                               |
      +---------------+---------------+
                      |
                      v
            JSON Parsing
                      |
                      v
        Data Normalization & Cleaning
                      |
                      v
             Data Quality Checks
                      |
                      v
                SQL Database
                      |
            +---------+---------+
            |                   |
            v                   v
     EDA / Analysis     Streamlit Dashboard
```

**Apache Airflow** will orchestrate the data ingestion, processing, validation, and loading tasks.

**Docker** will provide a reproducible runtime environment for the application and pipeline components.

## 5. Technology Stack

| Category | Technology | Purpose |
|---|---|---|
| Programming | Python 3.11 | Data ingestion and processing |
| API Integration | Requests | Retrieve NASA data |
| Data Processing | Pandas | Clean and transform data |
| Database | SQL (database engine TBD) | Store and query structured records |
| Orchestration | Apache Airflow | Manage DAG tasks and dependencies |
| Infrastructure | Docker / Docker Compose | Reproducible execution |
| Environment Management | Conda | Local development environment |
| EDA | Jupyter Notebook | Data exploration |
| Visualization | Plotly | Interactive charts |
| Dashboard | Streamlit | Interactive user interface |
| Testing | Pytest | Automated validation |
| Version Control | Git / GitHub | Collaboration and source control |

## 6. Repository Structure

```text
400_Data-engineering_project/
|
|-- README.md
|-- .gitignore
|-- .dockerignore
|-- .env.example
|-- environment.yml
|-- requirements.txt
|-- requirements-airflow.txt
|-- Dockerfile
|-- docker-compose.yml
|
|-- src/
|   |-- __init__.py
|   |-- apis/
|   |   |-- __init__.py
|   |   |-- apod_client.py
|   |   `-- image_library_client.py
|   |
|   |-- processing/
|   |   |-- __init__.py
|   |   |-- normalize.py
|   |   `-- validate.py
|   |
|   |-- database/
|   |   |-- __init__.py
|   |   |-- db.py
|   |   |-- load_data.py
|   |   `-- queries.py
|   |
|   `-- pipeline/
|       |-- __init__.py
|       `-- run_log.py
|
|-- dags/
|   `-- nasa_pipeline.py
|
|-- sql/
|   `-- schema.sql
|
|-- notebooks/
|   |-- 01_data_profiling.ipynb
|   `-- 02_exploratory_analysis.ipynb
|
|-- app.py
|-- pages/
|   |-- 01_APOD.py
|   `-- 02_Explore_Images.py
|
|-- data/
|   |-- raw/
|   `-- processed/
|
|-- tests/
|   |-- fixtures/
|   |-- test_api.py
|   |-- test_processing.py
|   |-- test_database.py
|   `-- test_pipeline.py
|
|-- docs/
|   |-- architecture.md
|   `-- project_status.md
|
`-- deck/
    `-- README.md
```

This represents the target repository structure. Some files and components are still under development.

Local `.env` files, sensitive information, database files, and generated datasets should not be committed to the repository.

## 7. Installation & Environment Setup

### Prerequisites

- Git
- Conda (Anaconda or Miniconda)
- Docker Desktop
- Python 3.11 (managed through Conda)

### Step 1 — Clone the Repository

```bash
git clone https://github.com/chirrene/400_Data-engineering_project.git
cd 400_Data-engineering_project
```

### Step 2 — Create the Conda Environment

```bash
conda env create -f environment.yml
conda activate nasa-space-explorer
```

### Step 3 — Install Python Dependencies

```bash
python -m pip install -r requirements.txt
```

### Step 4 — Configure Environment Variables

Copy the example configuration:

```bash
cp .env.example .env
```

Update `.env` as needed for your local environment.

**Never commit API keys, credentials, or other secrets to GitHub.**

## 8. Docker Setup

The repository includes a Dockerfile for building a consistent Python execution environment.

### Build the Docker Image

```bash
docker build -t nasa-space-explorer .
```

### Run the Initial Container Test

```bash
docker run --rm nasa-space-explorer
```

Expected output for the initial Docker configuration:

```text
NASA Space Explorer container ready!
```

This confirms that the base container can run. It does not yet verify the complete NASA ingestion pipeline.

Docker Compose and Airflow integration are under development.

## 9. Data Pipeline & DAG

The planned Apache Airflow DAG will coordinate the following tasks:

1. Fetch APOD data.
2. Fetch NASA Image and Video Library data.
3. Normalize and clean API responses.
4. Validate required fields and data quality.
5. Load processed records into the SQL database.
6. Log execution results and errors.

The DAG will manage task dependencies and help ensure a repeatable execution workflow.

**Current status:** In Development.

## 10. SQL Database & Data Quality

The project will store normalized NASA metadata in a relational database.

Planned functionality includes:

- Defining tables and primary keys.
- Inserting and retrieving NASA records.
- Preventing unwanted duplicate records.
- Checking missing and invalid values.
- Performing SQL queries for analysis.
- Supporting data retrieval for the dashboard.

The specific database engine and schema will be finalized during implementation.

## 11. Exploratory Data Analysis (EDA)

The project will include notebooks for profiling and exploring collected NASA data.

Planned analyses include:

- Dataset size and column types.
- Missing-value distributions.
- Duplicate-record analysis.
- Media type distribution.
- Historical record trends.
- Frequently occurring topics and keywords.

EDA results will help identify data quality issues and guide visualization design.

## 12. Interactive Streamlit Dashboard

The planned dashboard will enable users to explore NASA astronomy data through an interactive interface.

### Planned Features

**APOD Explorer**
- Browse astronomy pictures and descriptions.
- Filter by available publication dates.
- View image and media metadata.

**NASA Media Search**
- Search NASA images by keyword.
- Filter available results by media type.
- Explore returned metadata.

**Data Insights**
- Visualize collected record counts.
- Explore distributions and trends.
- Display selected EDA findings.

The dashboard will use processed data from the project pipeline and database.

**Current status:** In Development.

## 13. Testing

Automated tests will be developed to verify:

- API request handling.
- JSON response parsing.
- Data normalization.
- Required-field validation.
- Database operations.
- Pipeline execution and error handling.

The team will also perform end-to-end testing to confirm that the individual components work together.

## 14. Team Responsibilities

| Team Member | Primary Responsibilities |
|---|---|
| Irene | NASA API integration, data ingestion, normalization, GitHub management, project integration |
| Lize | Database design, SQL queries, data loading, and data quality |
| Andy | Apache Airflow DAG, Docker Compose, workflow automation, and execution logging |
| Chloe | EDA visualizations, Streamlit application, and interactive dashboard |
| All Members | Testing, documentation, integration, and final presentation |

## 15. Development Status

| Component | Status |
|---|---|
| GitHub Repository | Initial setup completed |
| Conda Environment | Initial setup completed |
| Docker Base Environment | Initial smoke test passed |
| Environment Configuration | Initial setup completed |
| NASA APOD API | In Development |
| NASA Image & Video Library API | In Development |
| Data Processing & Normalization | Planned |
| SQL Database | Planned |
| Airflow DAG | Planned |
| EDA | Planned |
| Streamlit Dashboard | Planned |
| End-to-End Integration Testing | Planned |

Project status will be updated as components are implemented and verified.

## 16. Project Deliverables

The final project aims to provide:

1. A documented GitHub repository.
2. Working NASA API ingestion components.
3. Data cleaning and validation functions.
4. A SQL database with supporting queries.
5. An executable DAG with defined task dependencies.
6. A reproducible Docker-based runtime.
7. Exploratory data analysis and visualizations.
8. An interactive Streamlit dashboard.
9. Automated tests and an end-to-end demonstration.
10. A final project presentation.

## 17. References

- NASA Open APIs: https://api.nasa.gov/
- NASA APOD: https://science.nasa.gov/
- NASA Image and Video Library: https://images.nasa.gov/
- Apache Airflow: https://airflow.apache.org/
- Docker: https://docs.docker.com/
- Streamlit: https://docs.streamlit.io/
- Plotly: https://plotly.com/python/

---

**Northwestern University — MS in Machine Learning & Data Science**

*NASA Space Explorer | Data Engineering Final Project*
