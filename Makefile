.PHONY: run
run:
	@docker compose up -d postgres redis mongodb neo4j elasticsearch lab1
	@.venv/bin/uvicorn gateway.main:create_app --factory --reload --port 8000
