# -*- mode: python -*-
# -*- coding: utf-8 -*-
#
# Copyright © 2019-2025  CINCH Enterprises, Ltd and Rod Pullmann.  All rights reserved.

""" Example monolithic service controller class implementation. """
# pylint:disable=wrong-import-position

from pathlib import Path
from http import HTTPStatus
from uuid import uuid4

from swagtools_skeleton_client.skeleton_client.client import APIClient
ServiceConfig = APIClient.ServiceConfig
from swagtools.swagger_base import SwaggerModel
from swagtools.resources.resource_base import (api, error_status_desc, resource_client, ResourceBase,
                                                authorization_check)
from swagtools.service_exceptions import (ServiceError, ServiceParameterError)

SERVICE_PASSWORD = 'vewwy-secwet'


class Controller:
    """ Generic example controller to illustrate Swagger UI construction. """

    # An example model.
    BLOB_MODEL = SwaggerModel.define(api, 'ServiceBLOB', dict(
        blob_string1=dict(type=str, field=dict(description="a mutable string value")),  # noqa:E126
        blob_int1=dict(type=int, field=dict(description="an integer value")),
        blob_flag=dict(type=bool, field=dict(description="a flag value")),
        blob_const=dict(type=str, field=dict(readOnly=True, description="a constant string value")),
    ))

    def __init__(self):
        self.service_state = 'INITIALIZED'
        self.file = None
        self.blob = None
        self.blob_client = None
        self.creds = {}

    # noinspection PyMethodMayBeStatic
    def is_hosted_remotely(self):
        """
        Determines whether this code is running on a remote system vs on a local development system.

        :return: "Code is running on a remote server system."
        :rtype:  bool

        :http: GET
        """
        return ServiceConfig.IS_HOSTED_REMOTELY

    def authorize_basic(self, username=None, password=''):
        """
        Provide credentials for resources requiring basic authorization.

        :param username: Username for authorization request (None => validate password without username)
        :type  username: Union(str, None)
        :param password: Plaintext or base64-encoded password (for `username` if supplied)
        :type  password: Password

        :return: "Credentials are valid."
        :rtype:  bool

        :http: POST

        .. note::
         * This is a very basic, low-security authorization mechanism; do not use to secure mission-critical data.
         * This is provided for SDK use only; from the Swagger GUI, use the [Authorize] button above instead.
        """
        valid = authorization_check(username=username, password=password, resource_token=SERVICE_PASSWORD)
        if valid:
            self.creds[resource_client().name] = True
        return HTTPStatus.OK if valid else HTTPStatus.UNAUTHORIZED, valid

    def authorize_token(self, username=None, password=''):
        """
        Provide credentials to create a token that can be used for resources requiring bearer token authorization.

        :param username: Username for authorization request (None => validate password without username)
        :type  username: Union(str, None)
        :param password: Plaintext or base64-encoded password (for `username` if supplied)
        :type  password: Password

        :return: Token associated with client (None => credentials are invalid)
        :rtype:  Union(str, None)

        :http: POST

        .. note::
         * This is a very basic, low-security authorization mechanism; do not use to secure mission-critical data.
        """
        valid = token = authorization_check(username=username, password=password, resource_token=SERVICE_PASSWORD)
        if valid:
            token = self.creds[resource_client().name] = str(uuid4())
        return token or None

    # noinspection PyMethodMayBeStatic
    def get_service_config(self, key=None):
        """
        Retrieves service configuration.

        :param key: Configuration key to retrieve (automatically translated to uppercase); None => all config items
        :type  key: Union(str, None)

        :return: Representation of service configuration
        :rtype:  dict

        :http: GET
        """
        if key:
            key = key.upper()
        cfg = {k: (v if v is None or isinstance(v, (str, int, float, list, dict)) else repr(v))
               for k, v in vars(ServiceConfig).items()
               if not k.startswith('_') and not callable(v)}
        return {key: cfg.get(key, NotImplemented)} if key else cfg

    # noinspection PyMethodMayBeStatic
    def set_service_config(self, key, value=None):
        """
        Sets a service configuration item.

        :param key:   Configuration key to set (automatically translated to uppercase)
        :type  key:   str
        :param value: Configuration value to set (None => delete key from configuration)
        :type  value: Union(str, None)

        :http: POST

        .. note::
         * This is for demo purposes only, and has no effect on the running service.
        """
        key = key.upper()
        if key.startswith('_'):
            raise ServiceParameterError("Cannot specify a private configuration member '{}'".format(key))

        if value:
            setattr(ServiceConfig, key, value.strip())
        elif hasattr(ServiceConfig, key):
            ServiceConfig.__delattr__(key)

    def get_service_state(self):
        """
        Retrieves the "state" of the service.

        :return: Service "state"
        :rtype:  str

        :http: GET
        """
        return self.service_state

    def set_service_state(self, state):
        """
        Sets the current "state" of the service.

        :param state: "State" to set
        :type  state: str

        :http: POST

        ..note::
         * "State" here is an arbitrary string used simply for illustrative purposes.
        """
        self.service_state = state

    def file_upload(self, file, save=False):
        """
        Uploads a file to the service.

        :param file: Client-side file specification to upload (type==File below => use file browser)
        :type  file: File
        :param save: "Save file to filesystem."
        :type  save: bool

        :http: POST
        """
        self.file = file
        filespec = Path('/tmp').joinpath(file.filename)
        if filespec.exists():
            raise ServiceError("File already exists")
        if save:
            file.save(filespec.as_posix())

    def store_blob(self, blob):
        """
        Stores a BLOB (arbitrary object) within this service as a singleton
        (only one BLOB can be stored for the service, among all service clients).

        :param blob: BLOB to store
        :type  blob: ServiceBLOB

        :http: POST
        :header X-Authorization: Authorization token for request
        """
        cred = self.creds.get(resource_client().name, '')
        if cred is not True:
            if not authorization_check(resource_token=cred or SERVICE_PASSWORD):
                ResourceBase.abort_request(*error_status_desc(HTTPStatus.UNAUTHORIZED, "Authorization required"))
        if self.blob:
            ResourceBase.abort_request(*error_status_desc(HTTPStatus.CONFLICT, "BLOB already stored"))
        self.blob = blob
        self.blob_client = resource_client().name
        return HTTPStatus.NO_CONTENT

    def get_blob(self):
        """
        Retrieves the BLOB (arbitrary object) stored to this service, if any.

        :return: BLOB stored to this service (None => no BLOB stored)
        :rtype:  Union(ServiceBLOB, None)

        :http: GET
        """
        return (HTTPStatus.OK if self.blob_client else HTTPStatus.NO_CONTENT), vars(self.blob) if self.blob else None

    def get_blob_client(self):
        """
        Retrieves the client ID of the client that stored the BLOB (arbitrary object)
        to this service, if any.

        :return: Client ID of BLOB storer (None => no BLOB stored)
        :rtype:  Union(str, None)

        :http: GET
        """
        return (HTTPStatus.OK if self.blob_client else HTTPStatus.NO_CONTENT), self.blob_client
