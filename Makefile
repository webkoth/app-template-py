# Единая точка входа. `make check` прогоняется перед любым коммитом.
#
# Табуляции в начале строк рецептов обязательны — это Make, пробелы он не
# принимает. Переменные шелла экранируются двойным $$: одинарный $ Make
# забирает себе.

.PHONY: install check check-backend check-frontend check-openapi openapi \
        dev dev-backend dev-frontend migrate migrate-up

install:
	cd backend && uv sync
	@if [ -f frontend/package.json ]; then cd frontend && npm ci; fi

# Фронтенд проверяется, только когда он установлен. Проверка по
# node_modules, а не по package.json: пропустить надо и когда фронтенда ещё
# нет, и когда забыли `make install` — во втором случае npx полез бы в сеть
# и упал бы невнятно. Пропуск громкий: молчаливый однажды скроет поломку.
check: check-backend
	@if [ -d frontend/node_modules ]; then \
		$(MAKE) check-frontend; \
	else \
		echo "== фронтенд не установлен, его проверки пропущены =="; \
		echo "   поставить: make install"; \
	fi

check-backend:
	cd backend && uv run ruff format --check .
	cd backend && uv run ruff check .
	cd backend && uv run mypy app
	cd backend && uv run --group lint lint-imports --config .importlinter
	cd backend && uv run pytest

check-frontend: check-openapi
	cd frontend && npx tsc --noEmit
	cd frontend && npm run test

# Расхождение контракта ловится здесь: бэкенд поменял схему, фронт не
# перегенерировал типы — красный прогон на ветке, а не сюрприз в бою.
check-openapi:
	cd backend && uv run python -m app.openapi > /tmp/openapi.json
	cd frontend && npx openapi-typescript /tmp/openapi.json -o src/api/schema.d.ts.new
	@diff -q frontend/src/api/schema.d.ts frontend/src/api/schema.d.ts.new > /dev/null \
		|| { rm -f frontend/src/api/schema.d.ts.new; \
		     echo "Типы клиента разошлись со схемой. Выполни: make openapi"; \
		     exit 1; }
	@rm -f frontend/src/api/schema.d.ts.new

openapi:
	cd backend && uv run python -m app.openapi > /tmp/openapi.json
	cd frontend && npx openapi-typescript /tmp/openapi.json -o src/api/schema.d.ts

dev-backend:
	cd backend && uv run uvicorn app.main:app --reload --port 8000

dev-frontend:
	cd frontend && npm run dev

# Бэкенд уходит в фон, фронтенд держит передний план. set -m кладёт фоновую
# задачу в свою группу процессов, а trap убивает группу целиком: без этого
# uvicorn пережил бы выход и остался бы висеть на порту 8000, а следующий
# `make dev` падал бы с «address already in use» без понятной причины.
dev:
	@echo "Бэкенд: http://127.0.0.1:8000   Фронтенд: http://127.0.0.1:5173"
	@set -m; \
	(cd backend && exec uv run uvicorn app.main:app --reload --port 8000) & \
	BACK=$$!; \
	trap "kill -- -$$BACK 2>/dev/null || kill $$BACK 2>/dev/null" EXIT INT TERM; \
	cd frontend && npm run dev

# m= обязателен: alembic revision без имени создаёт файл со случайным
# именем, и через месяц история миграций нечитаема.
migrate:
	@test -n "$(m)" || { echo "нужно имя: make migrate m=<слаг>"; exit 1; }
	cd backend && uv run alembic revision --autogenerate -m "$(m)"
	@echo ""
	@echo "ПРОЧИТАЙ сгенерированную миграцию глазами перед применением."
	@echo "Alembic не видит переименований: показывает удаление плюс"
	@echo "добавление, и данные колонки теряются молча."

migrate-up:
	cd backend && uv run alembic upgrade head
