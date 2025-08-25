# -*- mode: python -*-
# -*- coding: utf-8 -*-
#
# Copyright © 2019-2025  CINCH Enterprises, Ltd and Rod Pullmann.  All rights reserved.

"""
API Resource Group: Example resource group for specific Service Operations.
"""
from http import HTTPStatus

from flask_restx import fields

from swagtools.resources.resource_base import (api, define_api_resource)
from swagtools.controller import Controller

namespace = api.namespace('operations', description=__doc__.strip())  # ('operations' here would be specific group name)

define_api_resource(namespace, Controller.get_service_config, methods=('GET',))
define_api_resource(namespace, Controller.set_service_config)
define_api_resource(namespace, 'set_service_state', route='service_state',
                    methods=dict(GET=Controller.get_service_state,
                                 POST=Controller.set_service_state))
define_api_resource(namespace, Controller.file_upload)
define_api_resource(namespace, methods=dict(POST=(Controller.store_blob, 'do_store_blob')),
                    route='blob', auth='basic apikey',  # (support both)
                    responses=((HTTPStatus.NO_CONTENT, "BLOB successfully stored"),
                               (HTTPStatus.CONFLICT, "BLOB already set by another client"),
                               ))
define_api_resource(namespace, methods=dict(GET=(Controller.get_blob, 'get_stored_blob')),
                    route='blob',
                    responses=((HTTPStatus.OK, "BLOB stored previously", Controller.BLOB_MODEL),
                               (HTTPStatus.NO_CONTENT, "No BLOB stored"),
                               ))
define_api_resource(namespace, Controller.get_blob_client, methods=('GET',),
                    responses=((HTTPStatus.OK, "Client ID for client storing BLOB", fields.String),
                               (HTTPStatus.NO_CONTENT, "No BLOB stored"),
                               ))
