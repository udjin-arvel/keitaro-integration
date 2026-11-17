.PHONY: install backend client test up down

install:
	python -m pip install -r backend/requirements.txt
	cd client && npm install

backend:
	cd backend && uvicorn main:app --reload --host 0.0.0.0 --port 8000

client:
	cd client && npm run dev

test:
	cd backend && python -m pytest
	cd client && npm test

up:
	docker compose up --build

down:
	docker compose down