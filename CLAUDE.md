# Fond

Deployen gaat automatisch: push naar main na groene tests; de server zet het binnen 5 minuten live als CI slaagt en /health werkt. Wijzig docker-compose.yml en Dockerfile alleen als Pieter erom vraagt. Databasemigraties moeten achterwaarts compatibel zijn.

Tests: `uv run pytest`; lint: `uv run ruff check .`
