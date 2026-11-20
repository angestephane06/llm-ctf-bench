PY ?= .venv/bin/python
CONFIG ?= configs/campaign.yaml
IMAGE ?= ctfbench-sandbox:latest

.PHONY: setup lint test test-docker image fetch eval smoke report dashboard

setup:            ## virtualenv + locked dependencies
	python3 -m venv .venv
	.venv/bin/pip install -q uv
	.venv/bin/uv pip install --python $(PY) -e ".[dev,dashboard]"

lint:
	$(PY) -m ruff check .
	$(PY) -m ruff format --check .
	$(PY) -m mypy

test:             ## unit tests, no Docker or GPU needed
	$(PY) -m pytest -m "not docker" -q

test-docker: image  ## sandbox security tests (network, user, timeout, cleanup)
	$(PY) -m pytest -m docker -q

image:
	docker build -f docker/sandbox.Dockerfile -t $(IMAGE) .

fetch:            ## download the 15 tasks from the pinned upstream commit
	$(PY) -m ctfbench fetch-tasks

smoke: image      ## scripted models in the real sandbox, no GPU
	$(PY) -m ctfbench run configs/smoke.yaml

eval: image fetch ## full campaign (needs Ollama and the models)
	$(PY) -m ctfbench run $(CONFIG)

dashboard:
	$(PY) -m streamlit run dashboard/app.py
