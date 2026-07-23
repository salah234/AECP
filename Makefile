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
	# --env-file is required here: Compose only reads a .env for its own
	# ${VAR} interpolation (e.g. TARGET_REPO_HOST_PATH in the agents
	# volume mount) from the compose file's own directory by default,
	# never from the repo root — a different mechanism than each
	# service's env_file: directive, which only injects vars into the
	# container's process, not into the compose file's own templating.
	docker compose --env-file .env -f deploy/docker/docker-compose.yml up --build

dev-down:
	docker compose --env-file .env -f deploy/docker/docker-compose.yml down -v

migrate: ## Apply Postgres migrations for taskgraph, state, observability
	@echo "wire to your migration runner of choice (e.g. dbmate, atlas) once one is chosen"
