#!/usr/bin/env python3
# -*- mode: python -*-
# -*- coding: utf-8 -*-
#
# Copyright © 2019-2025 CINCH Enterprises, Ltd. and Rod Pullmann.  All rights reserved.

"""
setuptools/pip installer for Swagger Tools.

.. note::
 * See :function:`pyutils.setup.setup()` notes for optional envirosym definitions to customize install.
"""

from pathlib import Path
from configparser import ConfigParser

# noinspection PyPackageRequirements,PyUnresolvedReferences
from cinch_pyutils.setup import setup
# noinspection PyPackageRequirements,PyUnresolvedReferences
from cinch_pyutils.pip import run_pip

import swagtools

THISDIR = Path(__file__).resolve().parent

config = ConfigParser()
config.read(Path(THISDIR, '.gitmodules'))
SUPPLEMENTAL_PACKAGES = [p for p in [config.get(s, 'path', fallback=None) for s in config.sections()] if p]

# noinspection PyTypeChecker
setup(
    THISDIR,
    version=swagtools.__version__,
    description="OpenAPI (Swagger) RESTful API Skeleton Example",
    url="https://github.com/cinchent/swagtools",
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
    python_requires='>=3.5, <4',
    external_packages=False,
    supplemental_packages=['swagtools_skeleton_client'] + SUPPLEMENTAL_PACKAGES,
    executables=([__file__, 'swagtools/app.py'] +
                 list(THISDIR.rglob('*.sh'))),
)

for pkg in SUPPLEMENTAL_PACKAGES:
    run_pip(['install', '--editable', THISDIR.joinpath(pkg)])
