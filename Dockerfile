FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /srv
COPY app/requirements.txt app/requirements.txt
RUN pip install -r app/requirements.txt
COPY alembic.ini ./
COPY migrations migrations
COPY app app
RUN useradd --system --uid 10001 --no-create-home etagi
USER etagi
EXPOSE 8000
CMD ["uvicorn", "app.api.application:app", "--host", "0.0.0.0", "--port", "8000"]
