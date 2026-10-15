FROM node:22-alpine AS portal
WORKDIR /portal
COPY frontend/demo-portal/package*.json ./
RUN npm ci
COPY frontend/demo-portal/ ./
RUN npm run build

FROM python:3.12-slim
WORKDIR /app
COPY services/core-api/requirements.txt /app/requirements.txt
RUN pip install --no-cache-dir -r requirements.txt
COPY services /app/services
COPY scripts /app/scripts
COPY tests /app/tests
COPY docs /app/docs
COPY frontend/demo-portal/e2e /app/frontend/demo-portal/e2e
COPY pyproject.toml /app/pyproject.toml
COPY --from=portal /portal/dist /app/frontend/demo-portal/dist
RUN useradd --create-home govflow && chown -R govflow:govflow /app
USER govflow
ENV PYTHONPATH=/app/services/core-api
EXPOSE 8014
CMD ["sh", "scripts/container-start.sh"]
