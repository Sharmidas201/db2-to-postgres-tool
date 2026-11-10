FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    STREAMLIT_SERVER_HEADLESS=true \
    STREAMLIT_SERVER_ADDRESS=0.0.0.0 \
    STREAMLIT_SERVER_PORT=8501

WORKDIR /app

COPY requirements-docker.lock ./requirements-docker.lock
RUN pip install --no-cache-dir -r requirements-docker.lock

COPY --chown=10001:10001 . /app
RUN useradd --create-home --uid 10001 assessment \
    && mkdir -p /home/assessment/.azure_migration_assistant \
    && chown -R assessment:assessment /home/assessment
USER assessment

EXPOSE 8501
CMD ["streamlit", "run", "app.py"]
