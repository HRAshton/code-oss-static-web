PYTHON ?= python3
RUFF ?= ruff
PYRIGHT ?= pyright
SHELLCHECK ?= shellcheck
RUBY ?= ruby

PYTHON_PATHS := scripts tests
SHELL_SCRIPTS := build.sh package.sh

.PHONY: check format format-check lint typecheck shellcheck syntax schema config workflow-yaml test policy

check: format-check lint typecheck shellcheck syntax schema config workflow-yaml test policy

format:
	$(RUFF) format $(PYTHON_PATHS)

format-check:
	$(RUFF) format --check $(PYTHON_PATHS)

lint:
	$(RUFF) check $(PYTHON_PATHS)

typecheck:
	$(PYRIGHT)

shellcheck:
	$(SHELLCHECK) $(SHELL_SCRIPTS)

syntax:
	$(PYTHON) -m compileall -q scripts tests
	@for file in tests/e2e/*.cjs tests/fixtures/web-extension/*.js; do node --check "$$file"; done

schema:
	$(PYTHON) scripts/validate_json_schema.py

config:
	$(PYTHON) scripts/validate_config.py

workflow-yaml:
	$(RUBY) scripts/check_workflow_yaml.rb

test:
	$(PYTHON) -m unittest discover -s tests -v

policy:
	$(PYTHON) scripts/check_policy.py
