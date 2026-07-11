SERVICES := coordinator taskgraph agents state integration observability gateway

.PHONY: install lint typecheck test proto-gen dev-up dev-down migrate

install: ## Install every service's dependencies (editable, incl. platform)
	@for svc in $(SERVICES); do \
		(cd $$svc && uv pip install -e . --group dev) || exit 1; \
	done
	@cd platform && uv pip install -e . --group dev
	@cd dashboard && npm install

lint:
	@for svc in $(SERVICES); do (cd $$svc && ruff check .) || exit 1; done

typecheck:
	@for svc in $(SERVICES); do (cd $$svc && mypy .) || exit 1; done
	@cd dashboard && npm run typecheck

test:
	@for svc in $(SERVICES); do (cd $$svc && pytest) || exit 1; done

proto-gen: ## Regenerate Python/TypeScript stubs from /proto — requires buf
	cd proto && buf generate

dev-up: ## Boot the full local dev topology
	docker compose -f deploy/docker/docker-compose.yml up --build

dev-down:
	docker compose -f deploy/docker/docker-compose.yml down -v

migrate: ## Apply Postgres migrations for taskgraph, state, observability
	@echo "wire to your migration runner of choice (e.g. dbmate, atlas) once one is chosen"
