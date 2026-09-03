.PHONY: test coverage lint demo serve

test:
	.venv/bin/pytest -q

coverage:
	.venv/bin/coverage run -m pytest -q
	.venv/bin/coverage report

lint:
	.venv/bin/ruff check .

demo:
	.venv/bin/python -m fieldbridge

serve:
	.venv/bin/uvicorn fieldbridge.api:app --port 8080
