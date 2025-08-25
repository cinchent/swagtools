#!/usr/bin/env bash
# Configuration parameters related to the API Skeleton Service.
# NOTE: This is a multi-use file -- both a 'bash' shell script and a Python module; use syntax accordingly.

IS_HOSTED_REMOTELY=False  # (set True if server is hosted other than as 'localhost')

# Flask definitions:
FLASK_DEBUG=True  # Do not use debug mode in production
FLASK_HOST='localhost'
FLASK_PORT=5000

# HTTP Server definitions (for remote hosting):
HTTP_SERVICE_HOST='my_server.some_domain.net'   # @@@ (or wherever server is hosted remotely)
HTTP_SERVICE_PORT=8000                          # @@@ (or whichever remote port is exposed)
HTTP_SERVICE_SOCKADDR="${HTTP_SERVICE_HOST}:${HTTP_SERVICE_PORT}"
HTTP_SERVICE_DOCPATH='/doc/'
HTTP_SERVICE_MAXINSTANCES=3

# HTTP Server API Version
VERSION='v1'
API_BASEPATH='/api/'
