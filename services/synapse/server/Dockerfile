# Stage 1: install dependencies into a venv
FROM python:3.12-slim AS builder
WORKDIR /build
RUN python -m venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"
COPY requirements.txt .
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt

# Stage 2: lean runtime image, non-root user
FROM python:3.12-slim AS runtime
RUN useradd --uid 1000 --no-create-home --shell /bin/false synapse
WORKDIR /app
COPY --from=builder /opt/venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"
COPY server.py .
EXPOSE 8080
USER synapse
CMD ["python", "server.py"]
