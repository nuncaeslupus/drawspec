ARSENAL_REPO    ?= https://github.com/nuncaeslupus/claude-arsenal.git
ARSENAL_REF     ?= v0.23.1
ARSENAL_PLUGINS ?= all

.PHONY: help sync build lint format test schema gallery clean update-skills

help:  ## list targets
	@grep -hE '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | sort | \
		awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-16s\033[0m %s\n", $$1, $$2}'

sync:  ## install the project and its dev dependencies
	uv sync --all-extras

build:  ## build the wheel and sdist
	uv build

lint:  ## ruff check + strict mypy
	uv run ruff check .
	uv run mypy .

format:  ## ruff format + autofix
	uv run ruff format .
	uv run ruff check --fix .

test:  ## run the test suite
	uv run pytest

schema:  ## regenerate the published JSON Schema from the field tables
	uv run python -m drawspec.schema

gallery:  ## render every reference document to docs/gallery and open the page
	uv run python tools/gallery.py

clean:  ## remove build and tool caches
	rm -rf dist build .mypy_cache .pytest_cache .ruff_cache
	find . -type d -name __pycache__ -exec rm -rf {} +

update-skills:  ## vendor claude-arsenal skills into .claude/skills (for CC web)
	@tmp=$$(mktemp -d); trap 'rm -rf $$tmp' EXIT; \
	git clone --depth 1 --branch $(ARSENAL_REF) $(ARSENAL_REPO) $$tmp >/dev/null 2>&1 && \
	bash $$tmp/scripts/vendor-skills.sh --src $$tmp --dest .claude/skills --plugins $(ARSENAL_PLUGINS)
