#!/usr/bin/env python3
""" Simple skeleton for scripts using Swagger Tools SDK directly. """
# pylint:disable=wrong-import-position,invalid-name

import sys
import os
from pathlib import Path
# noinspection PyPackageRequirements
import urllib3.exceptions

import swagtools
# Path to client SDK:
# pylint:disable=no-member
sys.path = [str(Path(swagtools.__file__).parents[1].joinpath('swagtools_skeleton_client/skeleton_client'))] + sys.path
# pylint: disable=import-error,wrong-import-order
# noinspection PyUnresolvedReferences
from client import (APIClient, SkeletonSDKException)

try:
    from client import (manager_api, operations_api)  # (AUTO_GEN=False)
except ImportError:
    # noinspection PyUnresolvedReferences
    from client import services_api  # (AUTO_GEN=True)
    manager_api = services_api
    operations_api = services_api
    operations_api.get_stored_blob = services_api.get_blob   # (no endpoint aliasing for AUTO_GEN)

SERVICE_HOST = os.getenv('HTTP_SERVICE_HOST',  # Host where Swagger API server is running:
                         'localhost')          # ('localhost' => use server running on local system)
SERVICE_PASSWORD = 'vewwy-secwet'

host = APIClient.init_sdk(host=SERVICE_HOST)
try:
    is_remote = manager_api.is_hosted_remotely()
except (SkeletonSDKException, urllib3.exceptions.MaxRetryError) as exc:
    sys.exit("Error: Cannot access Swagger API service on host '{}': {}".format(host, exc))
print("Host: {} (hosted {})".format(host, ("locally", "remotely")[bool(is_remote)]))

try:
    print("Service state: {}".format(operations_api.get_service_state()))
    operations_api.set_service_state("STARTED")
    print("Service state: {}".format(operations_api.get_service_state()))

    config_item = 'HTTP_SERVICE_PORT'
    print("Service config: {}".format(operations_api.get_service_config()))
    print("Service config item: {}".format(operations_api.get_service_config(key=config_item)))  # (pass-by-keyword)
    operations_api.set_service_config(config_item, value=9999)
    print("Service config item: {}".format(operations_api.get_service_config(key=config_item)))

    print("Service BLOB: {}".format(operations_api.get_stored_blob()))
    manager_api.do_authorize(password=SERVICE_PASSWORD)
    the_blob = dict(blob_string1="the BLOB string", blob_int1=42, blob_flag=True, blob_const="immutable")
    operations_api.do_store_blob(the_blob)
    print("Service BLOB: {}".format(operations_api.get_stored_blob()))
    print("Service BLOB client: {}".format(operations_api.get_blob_client()))
    try:
        operations_api.do_store_blob(the_blob)
    except SkeletonSDKException as exc:
        print("Expected failure: {}: {}".format(exc.reason, exc.body))
except SkeletonSDKException as exc:
    print("ERROR: {}: {}".format(exc.reason, exc.body), file=sys.stderr)
