#!/usr/bin/env python3
# -*- mode: python -*-
# -*- coding: utf-8 -*-
#
# Copyright © 2019-2025  CINCH Enterprises, Ltd and Rod Pullmann.  All rights reserved.

"""
setuptools/pip installer for Swagger Tools Skeleton Client SDK.

.. note::
 * See :function:`pyutils.setup.setup()` notes for optional envirosym definitions to customize install.
"""

import os
from pathlib import Path

from setuptools import find_packages

# noinspection PyPackageRequirements,PyUnresolvedReferences
from cinch_pyutils.setup import setup

import skeleton_client  # pylint:disable=import-error

THISDIR = Path(__file__).resolve().parent

os.chdir(THISDIR)  # (necessary for find_packages())
# noinspection PyTypeChecker
setup(
    THISDIR,
    version=skeleton_client.__version__,
    description="Client SDK for OpenAPI (Swagger) Example API",
    url="https://github.com/cinchent/swagtools/swagtools_skeleton_client",
    author="Rod Pullmann",
    author_email='rod@cinchent.com',
    license="MIT :: " + THISDIR.joinpath('LICENSE.txt').read_text(encoding='utf-8').split('\n')[0],
    classifiers=[
        "Development Status :: 5 - Production/Stable",
        "License :: OSI Approved :: MIT License",
        "Programming Language :: Python :: 3",
        "Intended Audience :: Developers",
        "Topic :: Software Development :: RESTful API",
        "Topic :: Software Development :: OpenAPI",
    ],
    keywords="rest restful api flask swagger openapi flask-restx server",
    packages=[t[0] for base in find_packages() for t in os.walk(base)
              if '__init__.py' in t[2] and str(Path(t[0]).name) != 'test'],
    python_requires='>=3.5, <4',
    external_packages=False,
)
