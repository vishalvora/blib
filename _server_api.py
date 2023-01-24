# Copyright (c) Databricks Inc.
# Distributed under the terms of the DB License (see https://databricks.com/db-license-source
# for more information).

from bamboolib._environment import LICENSES_SERVER
from bamboolib.helper import notification, log_setup, file_logger
from bamboolib.config import get_option

import requests
from requests.exceptions import ConnectionError

import json


class ErrorResponse:
    """
    Base class for an error response from the server. Contains the error message.
    """

    def has_error(self):
        return True

    def error_embeddable(self):
        raise NotImplementedError


class ConnectionErrorResponse(ErrorResponse):
    """When we can't reach the server."""

    def error_embeddable(self):
        log_setup("auth", "ConnectionErrorResponse", "unable to reach server")
        message = """
We were not able to reach our server. Please check your internet connection or try again later.<br>
If you need help, you can contact us via <a href="mailto:support+connection_server_error@8080labs.com" target="_blank">support@8080labs.com</a>
"""
        return notification(message, type="error")


class UnknownErrorResponse(ErrorResponse):
    """When we have an unknown error."""

    def error_embeddable(self):
        log_setup("auth", "UnknownErrorResponse", "unknown error")
        message = """
There was an unknown error when we were trying to reach our servers.<br>
Please try again later or contact us via <a href="mailto:support+unknown_server_error@8080labs.com" target="_blank">support@8080labs.com</a>
"""
        return notification(message, type="error")


class UnauthorizedResponse(ErrorResponse):
    """User is not authorized (wrong credentials)"""

    def error_embeddable(self):
        log_setup("auth", "UnauthorizedResponse", "email or key invalid")
        message = """
Either your email address or the license key is not valid.<br>
If you need help, you can contact us via <a href="mailto:support+unauthorized_server_error@8080labs.com" target="_blank">support@8080labs.com</a>
"""
        return notification(message, type="error")


class LicenseResponse:
    """License response object when we get a success message from the server."""

    def __init__(self, license):
        self.license = license

        seats = self.license.get("floating_seats")
        if type(seats) is str:
            # this is a fix in case that the API returns a json string
            try:
                seats = json.loads(seats)
            except:
                seats = []
        if type(seats) is not list:
            seats = []
        self.license["floating_seats"] = seats

    def has_error(self):
        return False


def _get_license_by_key(key):
    """GET license by license key."""
    SECRET = "U7qWdmQRVjvfb5HPRXKk"
    headers = {"secret": SECRET}
    payload = {"key": key}
    get_request = requests.get(
        f"{LICENSES_SERVER}/get_license_by_key.json",
        params=payload,
        headers=headers,
        verify=False,
    )
    return get_request


def _update_license_request(license_dict):
    """POST request. Update license on server."""
    SECRET = "U7qWdmQRVjvfb5HPRXKk"
    headers = {"secret": SECRET}
    payload = {"key": license_dict.get("key", ""), "license": json.dumps(license_dict)}

    post_request = requests.post(
        f"{LICENSES_SERVER}/update_license_by_key.json",
        data=payload,
        headers=headers,
        verify=False,
    )
    return post_request


def send_floating_limit_notification(license_dict):
    """POST request. Send notification to server."""
    try:
        SECRET = "U7qWdmQRVjvfb5HPRXKk"
        headers = {"secret": SECRET}
        payload = {"key": license_dict.get("key", "")}

        requests.post(
            f"{LICENSES_SERVER}/floating_limit_notification.json",
            data=payload,
            headers=headers,
            verify=False,
        )
    except:
        pass


def _handle_license_request(function, *args, **kwargs):
    """
    Helper function. Sends requests to the server and handles the reponses.

    :param function: function that sends a request to the server.
    """
    try:
        license_request = function(*args, **kwargs)
        # here are all the exceptions that we can handle
        # https://stackoverflow.com/questions/16511337/correct-way-to-try-except-using-python-requests-module
    except ConnectionError as error:
        if get_option("global.log_errors"):
            file_logger.exception("ConnectionError during license request")
        return ConnectionErrorResponse()

    if license_request.status_code == 200:
        return LicenseResponse(license_request.json())
    elif license_request.status_code == 401:
        return UnauthorizedResponse()
    else:
        return UnknownErrorResponse()


def get_license_from_server(user_email, key):
    return _handle_license_request(_get_license_by_key, key)


def update_license_on_server(license_dict):
    return _handle_license_request(_update_license_request, license_dict)


def sync_license_with_server(license_dict):
    try:
        return _handle_license_request(_get_license_by_key, license_dict.get("key", ""))
    except:
        if get_option("global.log_errors"):
            file_logger.exception("Exception during license sync request")
        return UnknownErrorResponse()
