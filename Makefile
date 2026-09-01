.PHONY: validate test build check serve update

validate:
	python3 scripts/validate.py

test:
	python3 -m unittest discover -s tests -v

build:
	python3 scripts/build_site.py

check: validate test
	python3 scripts/build_site.py --check

serve: build
	python3 -m http.server 8000

update:
	python3 scripts/crawl.py
	python3 scripts/validate.py
	python3 scripts/build_site.py
