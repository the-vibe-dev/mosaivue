.PHONY: test frontend build check release clean

test:
	PYTHONPATH=src pytest
	cd frontend && npm test

frontend:
	cd frontend && npm run typecheck && npm run build
	rm -rf src/mosaivue/static
	cp -a frontend/dist src/mosaivue/static

build: frontend
	python -m compileall -q src

check: build test
	python scripts/check_release.py
	for file in install.sh uninstall.sh installer/*.sh packaging/*.sh scripts/*.sh; do bash -n "$$file"; done

release: check
	packaging/build-release.sh dist

clean:
	rm -rf .pytest_cache .coverage coverage.xml dist build *.egg-info
	find . -type d -name __pycache__ -prune -exec rm -rf {} +
	cd frontend && npm run clean
