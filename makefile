.PHONY: test
test:
	python -m unittest discover -v

test_install:
	rm -rf env
	python -m venv env; source env/bin/activate; pip install .; python setup.py sdist bdist_wheel; 
test_install2:
	python -m venv env; source env/bin/activate; pip install .[Codec2]; python setup.py sdist bdist_wheel; 

