FROM python:3.12-slim

WORKDIR /app

ENV PYTHONPATH=/app
ENV PYTHONUNBUFFERED=1

COPY src/requirements.txt ./requirements.txt

RUN pip install --no-cache-dir -r requirements.txt

COPY src/app ./app
COPY tests/test_ventas.py ./tests/test_ventas.py

CMD ["pytest", "-v", "tests/test_ventas.py"]