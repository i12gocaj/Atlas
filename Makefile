# Atlas. Bootstrap reproducible de la demo.
# Requiere el entorno activado (. .venv/bin/activate) y Ollama corriendo con el
# modelo (ollama pull qwen2.5:7b). Las fases con LLM (brain) tardan unos minutos.

PY := PYTHONPATH=src python -m atlas.cli
EVENTS := data/events.jsonl

.PHONY: demo data brain dashboard doctor snapshot test serve clean help

help:
	@echo "Atlas, targets principales:"
	@echo "  make demo      regenera todo (datos + cerebro + dashboard) y valida"
	@echo "  make doctor    valida los invariantes de la demo (PASS/FAIL)"
	@echo "  make snapshot  congela el estado actual como respaldo versionado"
	@echo "  make serve     sirve el dashboard en http://localhost:8777"
	@echo "  make test      ejecuta los tests"

# Pipeline completo: datos deterministas, cerebro (LLM), dashboard, validacion.
demo: data brain dashboard doctor
	@echo "\nDemo lista. Sirve con 'make serve' y abre http://localhost:8777"

# Datos y senales (sin LLM, reproducible byte a byte). Incluye el control
# determinista: politica y deteccion de PII (no dependen del modelo).
data:
	$(PY) generate --out $(EVENTS)
	$(PY) signals --events $(EVENTS) --out data/signals
	$(PY) detect --events $(EVENTS) --out data/detection.json
	$(PY) policy --events $(EVENTS) --out data/policy.json
	$(PY) validate-pii --out data/validate_pii.json

# Cerebro: todo lo que depende del LLM local (tarda unos minutos).
brain:
	$(PY) brief --events $(EVENTS) --out data/brief.json
	$(PY) boilerplate --events $(EVENTS) --team Datos --out data/boilerplate.json
	$(PY) artifact --events $(EVENTS) --brief data/brief.json --out data/limit_proposal.json
	$(PY) validate-secrets --out data/validate_secrets.json
	$(PY) validate-intent --out data/validate_intent.json

dashboard:
	$(PY) export-dashboard --events $(EVENTS) --out dashboard/data.json

doctor:
	$(PY) doctor --events $(EVENTS)

# Congela el estado actual como respaldo versionado (dashboard/data.demo.*).
snapshot:
	$(PY) snapshot

test:
	PYTHONPATH=src python -m pytest -q

serve:
	$(PY) serve --port 8777

clean:
	rm -rf data dashboard/data.js dashboard/data.json
