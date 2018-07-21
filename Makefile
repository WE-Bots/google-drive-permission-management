init:
	pip install -r requirements.txt

test:
    pip install -r requirements-test.txt
	pytest

all: init test