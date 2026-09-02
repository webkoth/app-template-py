# Единая точка входа. `make check` прогоняется перед любым коммитом.
#
# Табуляции в начале строк рецептов обязательны — это Make, пробелы он не
# принимает. Переменные шелла экранируются двойным $$: одинарный $ Make
# забирает себе.

.PHONY: install check check-backend check-frontend check-openapi openapi \
        dev dev-backend dev-frontend revision migrate

install:
	cd backend && uv sync
	@if [ -f frontend/package.json ]; then cd frontend && npm ci; fi

# Признак готовности фронтенда — frontend/vitest.config.ts, а не наличие
# каталога: каркас SPA появляется раньше, чем типы клиента и тесты, и по
# каталогу ворота открылись бы на две задачи раньше, чем за ними есть что
# проверять. vitest.config.ts означает ровно нужное: фронтенд дособран, его
# тесты настроены. Пропуск громкий: молчаливый однажды скроет поломку.
#
# Если тесты настроены, а node_modules нет — это забытый `make install`, и
# это отказ, а не пропуск: иначе npx полез бы в сеть и упал бы невнятно.
check: check-backend
	@if [ -f frontend/vitest.config.ts ]; then \
		if [ -d frontend/node_modules ]; then \
			$(MAKE) check-frontend; \
		else \
			echo "== фронтенд настроен, но не установлен =="; \
			echo "   поставить: make install"; \
			exit 1; \
		fi; \
	else \
		echo "== фронтенд ещё не дособран, его проверки пропущены =="; \
	fi

check-backend:
	cd backend && uv run ruff format --check .
	cd backend && uv run ruff check .
	cd backend && uv run mypy app
	cd backend && uv run --group lint lint-imports --config .importlinter
	cd backend && uv run pytest

# tsc -b, а не tsc --noEmit. Корневой tsconfig.json — это `files: []` плюс
# references, и в не-build режиме tsc в references не заходит: проверка
# возвращала ноль на файле с `const probe: number = "строка"`. Замерено —
# --noEmit код 0, -b код 2. То есть фронтенд-типы не проверялись бы вовсе, а
# строка в Makefile выглядела бы сделанной работой. --force обязателен:
# без него tsc верит своему кэшу сборки и молчит.
check-frontend: check-openapi
	cd frontend && npx tsc -b --force
	cd frontend && npm run lint
	cd frontend && npm run test

# Расхождение контракта ловится здесь: бэкенд поменял схему, фронт не
# перегенерировал типы — красный прогон на ветке, а не сюрприз в бою.
#
# diff -u, а не -q: на совпадении оба молчат, а на расхождении -q печатает
# только «файлы различаются». В логе прогона это тупик — что именно уехало,
# видно лишь на своей машине, а смотрит туда как раз тот, у кого расхождение
# воспроизвелось только в CI.
check-openapi:
	cd backend && uv run python -m app.openapi > /tmp/openapi.json
	cd frontend && npx openapi-typescript /tmp/openapi.json -o src/api/schema.d.ts.new
	@diff -u frontend/src/api/schema.d.ts frontend/src/api/schema.d.ts.new \
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
#
# Фронтенд назван по имени, а не по адресу, и это не мелочь: Vite слушает
# «localhost», а на macOS это имя разрешается в IPv6 — замерено lsof, сокет
# один и он [::1]:5173. По http://127.0.0.1:5173 браузер получает отказ
# соединения, то есть напечатанный адрес не открывался вовсе. У бэкенда
# наоборот: uvicorn слушает 127.0.0.1:8000, туда же ходит прокси Vite.
dev:
	@echo "Бэкенд: http://127.0.0.1:8000   Фронтенд: http://localhost:5173"
	@set -m; \
	(cd backend && exec uv run uvicorn app.main:app --reload --port 8000) & \
	BACK=$$!; \
	trap "kill -- -$$BACK 2>/dev/null || kill $$BACK 2>/dev/null" EXIT INT TERM; \
	cd frontend && npm run dev

# revision создаёт миграцию, migrate её применяет — как в самом Alembic
# (`alembic revision` и `alembic upgrade`). Обратное именование, где migrate
# создаёт, привычно по Django и Rails и здесь стало бы ловушкой: человек с
# такой привычкой запустил бы `make migrate`, получил лишнюю пустую ревизию
# и не понял бы почему.
#
# m= обязателен: alembic revision без имени создаёт файл со случайным
# именем, и через месяц история миграций нечитаема.
revision:
	@test -n "$(m)" || { echo "нужно имя: make revision m=<слаг>"; exit 1; }
	cd backend && uv run alembic revision --autogenerate -m "$(m)"
	@echo ""
	@echo "ПРОЧИТАЙ сгенерированную миграцию глазами перед применением."
	@echo "Alembic не видит переименований: показывает удаление плюс"
	@echo "добавление, и данные колонки теряются молча."

migrate:
	cd backend && uv run alembic upgrade head
