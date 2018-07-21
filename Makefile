init:
	pip install -r requirements.txt

lint:
	pip install -r requirements-test.txt
	find . -maxdepth 1 -name \*.py -exec pycodestyle --max-line-length=120 --statistics --count {} +

test:
	tox

all: init lint test