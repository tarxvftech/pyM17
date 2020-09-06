#!/usr/bin/env python
import setuptools
from setuptools import setup

#for reference: https://github.com/navdeep-G/setup.py/blob/master/setup.py
#
NAME = 'M17'
DESCRIPTION = 'M17 radio (and radio-over-IP) protocol implementation'
URL = 'https://git.mmcginty.me/mike/pym17'
EMAIL = 'pyM17@tarxvf.tech'
AUTHOR = 'tarxvf'
REQUIRES_PYTHON = '>=3.8.0'
VERSION = '0.0.1'

REQUIRED=[
        "Cython",
        "numpy",
        "scipy",
        "soundcard",
        "bitstruct",
        "samplerate",
        "pycodec2"
        ]


long_description = DESCRIPTION


#look into sourcing VERSION from git tag
#what's this __version__ thing I'm seeing?
setuptools.setup(
    name=NAME,
    version=VERSION,
    description=DESCRIPTION,
    long_description=long_description,
    long_description_content_type='text/markdown',
    author=AUTHOR,
    author_email=EMAIL,
    python_requires=REQUIRES_PYTHON,
    url=URL,
    install_requires=REQUIRED,
    packages=setuptools.find_packages(),
    include_package_data=True,
    classifiers=[
        # Trove classifiers
        # Full list: https://pypi.python.org/pypi?%3Aaction=list_classifiers
        'Programming Language :: Python',
        'Programming Language :: Python :: 3',
        'Programming Language :: Python :: Implementation :: CPython',
    ]
    )

