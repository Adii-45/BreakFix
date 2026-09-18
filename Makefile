.PHONY: help setup seed validate test serve web build deploy clean

help:
	@echo "BreakFix"
	@echo "  make setup     - create .venv and install backend + frontend deps"
	@echo "  make seed      - verify and seed the 5 challenges into the local store"
	@echo "  make validate  - run the golden-set validation (PRD 12.3)"
	@echo "  make test      - run the unit + integration test suite"
	@echo "  make serve     - run the local Lambda/API Gateway shim on :8000"
	@echo "  make web       - run the frontend dev server on :5173"
	@echo "  make build     - production build of the frontend"
	@echo "  make deploy    - deploy the backend to AWS (needs aws + sam CLIs)"

setup:
	python3 -m venv .venv
	.venv/bin/pip install -q --upgrade pip
	.venv/bin/pip install -q -r requirements.txt
	cd frontend && npm install

seed:
	BREAKFIX_STORAGE=local .venv/bin/python seed-data/author_challenges.py

validate:
	.venv/bin/python scripts/validate_golden_set.py

test:
	.venv/bin/python -m pytest tests -q

serve:
	.venv/bin/python backend/local_server.py --port 8000

web:
	cd frontend && npm run dev

build:
	cd frontend && npm run build

deploy:
	./scripts/deploy.sh

clean:
	rm -rf .localdb .aws-sam frontend/dist frontend/node_modules .venv
