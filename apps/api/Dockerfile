FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONPATH=/code/apps/api:/code/packages/shared:/code/packages/contracts:/code/packages/strategies:/code/packages/indicators:/code/packages/broker_adapters:/code/backtesting:/code/services

WORKDIR /code

COPY pyproject.toml README.md ./
COPY apps ./apps
COPY packages ./packages
COPY services ./services
COPY backtesting ./backtesting
COPY migrations ./migrations
COPY alembic.ini ./

RUN pip install --no-cache-dir \
    "SQLAlchemy>=2.0.52" \
    "Alembic>=1.19.1" \
    "FastAPI>=0.141.1" \
    "psycopg[binary]>=3.2" \
    "uvicorn>=0.30" \
    "pydantic-settings>=2.0" \
    "argon2-cffi>=23"

EXPOSE 8000

CMD ["uvicorn", "alpha_algo_api.main:app", "--host", "0.0.0.0", "--port", "8000"]
