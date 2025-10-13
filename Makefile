.PHONY: all
all: ## Show the available make targets.
	@echo "Usage: make <target>"
	@echo ""
	@echo "Targets:"
	@fgrep "##" Makefile | fgrep -v fgrep

.PHONY: clean
clean: ## Clean the temporary files.
	rm -rf .mypy_cache
	rm -rf .ruff_cache
	rm -rf .pytest_cache
	rm -rf tests/__pycache__
	rm -rf .coverage
	rm -rf local_data

.PHONY: black-check
black-check: ## Run black for code formatting, without fixing.
	poetry run black src --check

.PHONY: black-apply
black-apply: ## Run black and fix code formatting.
	poetry run black src

.PHONY: ruff-check
ruff-check: ## Run ruff for linting and code formatting, without fixing.
	poetry run ruff check src

.PHONY: ruff-apply
ruff-apply: ## Run ruff and fix linting and code formatting.
	poetry run ruff check --fix src

.PHONY: pylint
pylint: ## Run pylint for code analysis.
	poetry run pylint src

.PHONY: md-check
md-check: ## Run markdown linting using Markdownlint, without fixing.
	@echo "Running Markdownlint...";
	sh ./shell_scripts/md_lint.sh

.PHONY: md-apply
md-apply: ## Run markdown linting with Markdownlint and fix issues.
	@echo "Running Markdownlint fix...";
	sh ./shell_scripts/md_fix.sh

.PHONY: lint-check
lint-check:  ## Run Python linters and markdown linting without fixing.
	make black-check
	make ruff-check
	make pylint
	make md-check

.PHONY: lint-apply
lint-apply: ## Run Python linters and markdown linting.
	make black-apply
	make ruff-apply
	make pylint
	make md-apply

.PHONY: megalint
megalint:  ## Run the mega-linter.
	docker run --platform linux/amd64 --rm \
		-v /var/run/docker.sock:/var/run/docker.sock:rw \
		-v $(shell pwd):/tmp/lint:rw \
		oxsecurity/megalinter:v8

.PHONY: mypy
mypy:  ## Run mypy.
	poetry run mypy src

.PHONY: install
install:  ## Install the dependencies excluding dev.
	poetry install --only main --no-root

.PHONY: install-dev
install-dev:  ## Install the dependencies including dev.
	poetry install --no-root

.PHONY: test
test: ## Run the lambda tests.
	poetry run pytest -n auto --cov=src --cov-report term-missing --cov-fail-under=95
	