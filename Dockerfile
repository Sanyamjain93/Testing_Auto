# ── Stage 1: Build React frontend ─────────────────────────────────────────────
FROM node:20-slim AS frontend-build

WORKDIR /app/frontend
COPY frontend/package*.json ./
RUN npm ci
COPY frontend/ ./
RUN npm run build

# ── Stage 2: Python backend ────────────────────────────────────────────────────
FROM python:3.11-slim

WORKDIR /app

# System dependencies needed for some ML/PDF packages
RUN apt-get update && apt-get install -y --no-install-recommends \
        gcc \
        g++ \
        libgomp1 \
    && rm -rf /var/lib/apt/lists/*

# Install Python dependencies.
# Notes:
#   - python-dotenv is installed explicitly because requirement.txt lists the
#     wrong package name ("dotenv").
#   - PyTorch CPU-only wheel is used to keep the image size manageable.
COPY requirement.txt ./
RUN pip install --no-cache-dir \
        python-dotenv \
        --extra-index-url https://download.pytorch.org/whl/cpu \
        -r requirement.txt

# Copy project source
COPY . .

# Copy built frontend from Stage 1
COPY --from=frontend-build /app/frontend/dist ./frontend/dist

# Create runtime directories that the pipeline writes into
RUN mkdir -p data/sample_requirements logs scripts rag_data

EXPOSE 8000

# Run uvicorn from the project root so that relative imports resolve correctly.
CMD ["uvicorn", "backend.app:app", "--host", "0.0.0.0", "--port", "8000"]
