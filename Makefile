init:
	pip install -r requirements.txt

lint:
	pip install -r requirements-test.txt
	find . -maxdepth 1 -name \*.py -exec pycodestyle --ignore E501 {} +

test:
	tox

all: init lint test