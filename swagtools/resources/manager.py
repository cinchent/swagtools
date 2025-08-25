# -*- mode: python -*-
# -*- coding: utf-8 -*-
#
# Copyright © 2019-2025  CINCH Enterprises, Ltd and Rod Pullmann.  All rights reserved.

"""
API Resource Group: Service Management Operations
"""
from swagtools.resources.resource_base import (api, define_api_resource)
from swagtools.controller import Controller

namespace = api.namespace('manager', description=__doc__.strip())

define_api_resource(namespace, Controller.is_hosted_remotely, methods=('GET',))
if 'basic' in api.authorizations:
    define_api_resource(namespace, Controller.authorize_basic)
if 'apikey' in api.authorizations:
    define_api_resource(namespace, Controller.authorize_token)
