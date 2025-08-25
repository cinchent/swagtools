# -*- mode: python -*-
# -*- coding: utf-8 -*-
#
# Copyright © 2019-2025  CINCH Enterprises, Ltd and Rod Pullmann. All rights reserved.

"""
Flask-RESTX definition for API Server.
"""
# pylint:disable=ungrouped-imports,wrong-import-position,wrong-import-order,invalid-name
import os

from swagtools.swagger_base import (SwaggerAPI, SwaggerResource)
from swagtools_skeleton_client.skeleton_client.client import APIClient
import logging
log = logging.getLogger()

ServiceConfig = APIClient.ServiceConfig
API_BASEPATH = ServiceConfig.API_BASEPATH
VERSION = ServiceConfig.VERSION
AUTHORIZATIONS = dict(basic={'type': 'basic'},  # (default if auth enabled)
                      apikey={'type': 'apiKey', 'in': 'header', 'name': 'Authorization'},
                      )

# "Demo API auto-generation."  (else define the API and its endpoints explicitly via `resources`)
AUTO_GEN = os.getenv('AUTO_GEN', 'false').lower() in ('1', 'true', 'on', 'yes')

ControllerSingletons = {}  # (global list of controller class instance singletons used)

API_INFO = dict(title="API Skeleton ({})".format(ServiceConfig.HTTP_SERVICE_HOST),
                description="Generic Swagger API Skeleton",
                basepath="/api/{}".format(VERSION), version=VERSION)

if AUTO_GEN:
    api = None
else:
    api = SwaggerAPI(doc=ServiceConfig.HTTP_SERVICE_DOCPATH, default_id=SwaggerResource.construct_sdk_funcname,
                     logger=log, authorizations=AUTHORIZATIONS, **API_INFO)


def generate_api(title, description, api_basepath=API_BASEPATH, api_version=VERSION, default_error_handler=None):
    """
    Dynamically auto-generates a Swagger API object to which controller class(es) can be bound.

    .. note::
     * See SwaggerAPI
    """
    global api  # pylint:disable=global-statement
    api = SwaggerAPI(version=api_version, title=title, description=description, basepath=api_basepath,
                     doc=ServiceConfig.HTTP_SERVICE_DOCPATH, default_id=SwaggerResource.construct_sdk_funcname,
                     logger=log, authorizations=AUTHORIZATIONS)

    if default_error_handler:
        # pylint:disable=unused-variable
        @api.errorhandler
        def wrapper(*args):
            return default_error_handler(*args)

    return api
