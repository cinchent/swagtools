#!/usr/bin/env python3
# -*- mode: python -*-
# -*- coding: utf-8 -*-
#

"""
setuptools/pip installer for swagger-python-codegen.
"""

import sys
from pathlib import Path
from setuptools import (setup, find_packages)

THISDIR = Path(__file__).resolve().parent
sys.path.insert(0, str(THISDIR))

# noinspection PyPackageRequirements,PyUnresolvedReferences
import swagger_python_codegen  # pylint:disable=wrong-import-position

setup(
    name='swagger-python-codegen',
    version=swagger_python_codegen.__version__,
    description="Swagger API SDK code generator for Python",
    url="https://github.com/cinchent/swagger-python-codegen",
    author="Rod Pullmann"
    author_email='rod@cinchent.com',
    classifiers=[
        "Development Status :: 5 - Production/Stable",
        "License :: Other/Proprietary License",
        "Programming Language :: Python :: 3",
        "Intended Audience :: Developers",
        "Topic :: Software Development :: Code Generator",
        "Topic :: Software Development :: RESTful API",
        "Topic :: Software Development :: RESTful SDK",
    ],
    packages=find_packages(),
    install_requires=Path(THISDIR, 'requirements.txt').read_text(encoding='utf-8'),
    keywords="rest restful api flask swagger openapi generator",
    scripts=[str(Path(THISDIR, 'bin/swagger-python-codegen'))],
)
