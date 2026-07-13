# Qualitätssicherung — Einstiegspunkt: `make qs` (läuft auch in der CI).
VENV = .venv/bin

.PHONY: qs lint typen test abdeckung

qs: lint typen test  ## Lint + Typprüfung + Tests (komplette QS)

lint:
	$(VENV)/ruff check bmtools tests

typen:
	$(VENV)/mypy

test:
	$(VENV)/python -m pytest --cov=bmtools

abdeckung:  ## Tests + HTML-Abdeckungsbericht (out/coverage/)
	$(VENV)/python -m pytest --cov=bmtools --cov-report=html
	@echo "Bericht: out/coverage/index.html"
