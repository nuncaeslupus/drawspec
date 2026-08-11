ARSENAL_REPO    ?= https://github.com/nuncaeslupus/claude-arsenal.git
ARSENAL_REF     ?= v0.23.1
ARSENAL_PLUGINS ?= all

.PHONY: help update-skills

help:  ## list targets
	@grep -hE '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | sort | \
		awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-16s\033[0m %s\n", $$1, $$2}'

update-skills:  ## vendor claude-arsenal skills into .claude/skills (for CC web)
	@tmp=$$(mktemp -d); trap 'rm -rf $$tmp' EXIT; \
	git clone --depth 1 --branch $(ARSENAL_REF) $(ARSENAL_REPO) $$tmp >/dev/null 2>&1 && \
	bash $$tmp/scripts/vendor-skills.sh --src $$tmp --dest .claude/skills --plugins $(ARSENAL_PLUGINS)
