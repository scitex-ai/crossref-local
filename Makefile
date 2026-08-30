# -*- mode: makefile-gmake -*-
# CrossRef Local - Root Makefile
#
# Quick Start:
#   make install   - Install package
#   make test      - Run tests
#   make status    - Show system status

.PHONY: help install venv dev test test-quick status clean \
        mcp-install mcp-uninstall mcp-status mcp-start mcp-stop mcp-restart mcp-logs

# Paths
PROJECT_ROOT := $(shell pwd)
SCRIPTS := $(PROJECT_ROOT)/scripts
VENV := $(PROJECT_ROOT)/.venv
PYTHON := $(VENV)/bin/python
PIP := $(VENV)/bin/pip

# Default target
.DEFAULT_GOAL := help

##@ Quick Start (New Users Start Here)

install: venv ## Install package (first time setup)
	@echo "Installing crossref-local..."
	@$(PIP) install -e . -q
	@echo ""
	@echo "✓ Package installed!"
	@echo ""
	@echo "Next steps:"
	@echo "  1. Verify the store resolves: make status"
	@echo "  2. Ingest recent works:       crossref-local update-db"
	@echo "  3. Test: crossref-local search 'machine learning'"

venv: ## Create virtual environment
	@if [ ! -d "$(VENV)" ]; then \
		echo "Creating virtual environment..."; \
		python3 -m venv $(VENV); \
	fi

dev: venv ## Install with dev dependencies
	@$(PIP) install -e ".[dev]" -q
	@echo "✓ Dev environment ready"

test: ## Run tests
	@$(PYTHON) -m pytest tests/ -v

test-quick: ## Run tests (quick, no output)
	@$(PYTHON) -m pytest tests/ -q

# --------------------------------------------------------------------------
# Corpus
#
# There are no corpus build targets any more. The corpus lives in the fleet's
# shared store primitive, not in a file this Makefile could create, index or
# check — so the bulk load, index creation, full-text index build, citations
# rebuild and integrity pragma that used to sit here have no artifact to act
# on. The corpus is ingested with the package instead:
#
#   crossref-local update-db             # incremental ingest (CrossRef REST API)
#   crossref-local update-db --dry-run   # count what would be upserted
#   crossref-local sync-stats            # recompute the exact-count cache
#   crossref-local status                # store resolution + cached counts
#
# See scripts/database/README.md for the old step -> new command mapping.

##@ General

help: ## Show this help
	@echo "CrossRef Local - Make Targets"
	@echo "=============================="
	@echo ""
	@awk 'BEGIN {FS = ":.*##"; printf "Usage: make \033[36m<target>\033[0m\n\n"} \
		/^[a-zA-Z_-]+:.*?##/ { printf "  \033[36m%-20s\033[0m %s\n", $$1, $$2 } \
		/^##@/ { printf "\n\033[1m%s\033[0m\n", substr($$0, 5) }' $(MAKEFILE_LIST)
	@echo ""
	@echo "Quick Start:"
	@echo "  make status                - Check system health"
	@echo "  crossref-local update-db   - Ingest recent works into the store"

##@ Status & Information

status: ## Show overall system status (run this first!)
	@$(SCRIPTS)/status.sh

##@ Maintenance

clean: ## Clean temporary files (NOT the corpus)
	@echo "Cleaning temporary files..."
	@find $(PROJECT_ROOT) -name "*.pyc" -delete
	@find $(PROJECT_ROOT) -name "__pycache__" -type d -exec rm -rf {} + 2>/dev/null || true
	@echo "Done. Corpus NOT affected."

##@ MCP Server (Remote Access)

mcp-install: ## Install MCP server as systemd service
	@$(SCRIPTS)/deployment/mcp/install.sh $(if $(PORT),--port $(PORT),)

mcp-uninstall: ## Remove MCP systemd service
	@$(SCRIPTS)/deployment/mcp/install.sh --uninstall

mcp-status: ## Show MCP server status
	@$(SCRIPTS)/deployment/mcp/status.sh

mcp-start: ## Start MCP server
	@sudo systemctl start crossref-mcp
	@echo "✓ MCP server started"

mcp-stop: ## Stop MCP server
	@sudo systemctl stop crossref-mcp
	@echo "✓ MCP server stopped"

mcp-restart: ## Restart MCP server
	@sudo systemctl restart crossref-mcp
	@echo "✓ MCP server restarted"

mcp-logs: ## Show MCP server logs (live)
	@journalctl -u crossref-mcp -f
