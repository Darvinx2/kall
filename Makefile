.PHONY: start stop restart ps health token lab1 logs seed down

# Всё только в Docker — никакого локального uvicorn. Gateway всегда
# ходит до lab1 по имени сервиса внутри сети compose; порт lab1 наружу
# не публикуется — снаружи достучаться до неё нельзя даже случайно.

start:
	docker compose up -d

stop:
	docker compose stop

restart: stop start

ps:
	docker compose ps

health:
	@curl -s http://localhost:8000/healthcheck; echo

token:
	@curl -s -X POST http://localhost:8000/auth/login \
		-d 'username=admin&password=admin-secret' \
		| python3 -m json.tool

lab1:
	@TOKEN=$$(curl -s -X POST http://localhost:8000/auth/login \
		-d 'username=admin&password=admin-secret' \
		| python3 -c 'import json,sys; print(json.load(sys.stdin)["access_token"])'); \
	curl -s -X POST http://localhost:8000/api/lab1/report \
		-H "Authorization: Bearer $$TOKEN" -H 'Content-Type: application/json' \
		-d '{"term":"нейронные сети","period_from":"2025-09-01","period_to":"2026-06-30","limit":10}' \
		| python3 -m json.tool

logs:
	docker compose logs -f gateway lab1

seed:
	docker compose --profile seed run --rm generator generate

down:
	docker compose down
