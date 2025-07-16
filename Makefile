.PHONY: help up down logs ps clean build

help:
@echo "Available commands:"
@echo "  make up       - Start all services"
@echo "  make down     - Stop all services"
@echo "  make logs     - Show logs"
@echo "  make ps       - Show running containers"
@echo "  make clean    - Clean volumes and containers"
@echo "  make build    - Build all services"

up:
docker-compose up -d

down:
docker-compose down

logs:
docker-compose logs -f

ps:
docker-compose ps

clean:
docker-compose down -v
rm -rf data/

build:
docker-compose build --no-cache

dev:
docker-compose up

test:
@echo "Running tests..."
# Add test commands here
