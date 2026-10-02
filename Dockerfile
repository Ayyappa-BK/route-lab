FROM node:24-alpine AS web
WORKDIR /build
COPY frontend/package*.json ./
RUN npm ci
COPY frontend/ ./
RUN npm run build
FROM python:3.13-alpine
WORKDIR /app
COPY backend/ ./backend/
COPY data/ ./data/
COPY --from=web /build/dist ./frontend/dist/
RUN adduser -D runner && mkdir /app/.data && chown runner /app/.data
USER runner
ENV HOST=0.0.0.0 PORT=8314 PYTHONUNBUFFERED=1
EXPOSE 8314
CMD ["python", "backend/server.py"]
