PYTHON ?= python3
RUFF ?= ruff
PYRIGHT ?= pyright
SHELLCHECK ?= shellcheck

PYTHON_PATHS := scripts tests
SHELL_SCRIPTS := build.sh package.sh

.PHONY: check format format-check lint typecheck shellcheck syntax test policy

check: format-check lint typecheck shellcheck syntax test policy

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

test:
	$(PYTHON) -m unittest discover -s tests -v

policy:
	$(PYTHON) scripts/check_policy.py
