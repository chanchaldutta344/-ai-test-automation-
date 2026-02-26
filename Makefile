SHELL := /bin/bash

.PHONY: dev start start-backend start-frontend stop-backend stop-frontend stop restart status install

start: dev

dev: start-backend start-frontend

start-backend:
	@./scripts/dev.sh start-backend

start-frontend:
	@./scripts/dev.sh start-frontend

stop-backend:
	@./scripts/dev.sh stop-backend

stop-frontend:
	@./scripts/dev.sh stop-frontend

stop:
	@./scripts/dev.sh stop

restart:
	@./scripts/dev.sh restart

status:
	@./scripts/dev.sh status

install:
	@echo "Installing backend deps..."
	@cd test-automation-backend && poetry install
	@echo "Installing frontend deps..."
	@cd test-automation-frontend && npm install
