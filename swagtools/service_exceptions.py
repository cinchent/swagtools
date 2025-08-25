# -*- mode: python -*-
# -*- coding: utf-8 -*-
#
# Copyright © 2019-2025  CINCH Enterprises, Ltd and Rod Pullmann.  All rights reserved.

""" Service exception class definitions. """

__all__ = ['ServiceParameterError', 'ServiceError']


class ServiceParameterError(Exception):
    """ Service operation parameter error. """


class ServiceError(Exception):
    """ Generic error executing service operation. """
