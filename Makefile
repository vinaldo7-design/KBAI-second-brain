# Mini Vinny: everything you run, in one place. `make` lists the commands.

.DEFAULT_GOAL := help
SHELL := /bin/bash
UV ?= uv
# Keep the environment out of iCloud: thousands of synced files slow everything down.
export UV_PROJECT_ENVIRONMENT ?= $(HOME)/.local/share/kbai/venv
export HF_HUB_OFFLINE ?= 1
RUN := $(UV) run --frozen --extra ml --extra dev
FAST_RUN := $(UV) run --frozen --extra dev

.PHONY: help install test test-fast lint verify ingest links notes-snapshot

help: ## List the commands
	@grep -E '^[a-z-]+:.*## ' $(MAKEFILE_LIST) | sed -E 's/:.*## /\t/' | expand -t 18

install: ## Install everything, including the ML models' libraries, and the pre-push check
	$(UV) sync --frozen --extra ml --extra dev
	git config core.hooksPath .githooks

test: ## All tests, including those that need your real vault
	$(RUN) pytest -q

test-fast: ## Tests that need no vault and no ML; this is what CI runs
	$(FAST_RUN) pytest -q -m "not live"

lint: ## Unused code and import boundaries
	$(FAST_RUN) ruff check .
	$(FAST_RUN) lint-imports

verify: ## Rebuild the graph and index, then run every check
	$(RUN) python -m kbai.notes_history "before verify"
	$(RUN) python vault_graph.py .
	$(RUN) python vault_embed.py
	$(RUN) python healthcheck.py --semantic
	$(RUN) python scripts/vault_audit.py
	$(MAKE) lint test

ingest: ## Push reviewed notes for a module: make ingest M=M1
	$(RUN) python scripts/ingest_push.py 07-attachments/oxford-inbox/_payloads_$(M).json
	$(RUN) python vault_graph.py .
	$(RUN) python healthcheck.py --semantic
	$(RUN) python scripts/vault_audit.py

links: ## Apply a reviewed list of links: make links FILE=links.json [DRY=1]
	$(RUN) python -m kbai.links $(FILE) $(if $(DRY),--dry-run)

notes-snapshot: ## Save the notes to their private history (outside iCloud, no remote)
	$(RUN) python -m kbai.notes_history "snapshot"
