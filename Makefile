.PHONY: test coverage lint audit release package verify demo serve rehearse record

test:
	.venv/bin/pytest -q

coverage:
	.venv/bin/coverage run -m pytest -q
	.venv/bin/coverage report --fail-under=80

lint:
	.venv/bin/ruff check .

audit:
	.venv/bin/pip-audit

release:
	.venv/bin/python scripts/validate_release.py

package:
	.venv/bin/python -m pip wheel --no-deps --no-build-isolation -w dist .

verify: test coverage lint audit release

demo:
	.venv/bin/python -m fieldbridge

serve:
	.venv/bin/uvicorn fieldbridge.api:app --port 8080

rehearse:
	.venv/bin/python scripts/record_demo.py --rehearse

record:
	.venv/bin/python scripts/record_demo.py
