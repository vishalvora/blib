# Copyright (c) Databricks Inc.
# Distributed under the terms of the DB License (see https://databricks.com/db-license-source
# for more information).


# EXPIRATION_LICENSE = {
#     "key": "EXPP-QC6T-W743-NT4F-ZFC4",
#     "license_logic": EXPIRATION_LICENSE_v1,
#     "refresh_max_delay_days": 14,
#     "refresh_interval_mins": 15,
#     "user_email": "florian.wetschoreck@gmail.com",
#     "user_email_check": True,
#     "expiration_date": "2019-12-25",
# }

# SINGLE_MACHINE_LICENSE = {
#     "key": "EXPP-QC6T-W743-NT4F-ZFC4",
#     "license_logic": SINGLE_MACHINE_LICENSE_v1,
#     "refresh_max_delay_days": 14,
#     "refresh_interval_mins": 15,
#     "user_email": "florian.wetschoreck@gmail.com",
#     "user_email_check": True,
#     "expiration_date": "2019-12-25",
#     "machine_fingerprint": "darwin;;;/Users/florianwetschoreck",
#     "machine_name": "Florian's MacBook Pro",
#     "activated": False,
#     "activation_count": 0,
#     "activation_max_count": 5,
# }


# Migration note: we can log out/invalidate all local licenses, when we change the encryption secret
# also, we can use an obscure S3 bucket for shipping bamboolib (and updates)


from cryptography.hazmat.backends import default_backend
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC
from cryptography.fernet import Fernet

import base64
import datetime as dt
import json
from functools import lru_cache
from pathlib import Path
import sys
import time

import ipywidgets as widgets

from bamboolib import _environment as env
from bamboolib._path import (
    BAMBOOLIB_LIBRARY_CONFIG_PATH,
    BAMBOOLIB_LIBRARY_INTERNAL_CONFIG_PATH,
)

from bamboolib.helper import (
    notification,
    activate_license,
    maybe_identify_segment,
    # calling the log methods during init of bamboolib leads to circular dependency errors
    # if the methods are only called later, then it is fine
    log_setup,
    log_error,
    execute_asynchronously,
)
from bamboolib.widgets import Button

from bamboolib._server_api import (
    get_license_from_server,
    update_license_on_server,
    sync_license_with_server,
    send_floating_limit_notification,
)

import bamboolib.config as config


NO_USER_EMAIL = "NO_USER_EMAIL"
KAGGLE_KERNEL_ANONYMOUS = "KAGGLE_KERNEL_ANONYMOUS"
BINDER_NOTEBOOK_ANONYMOUS = "BINDER_NOTEBOOK_ANONYMOUS"

DATETIME_FORMAT = "%Y-%m-%d %H:%M:%S %z %Z"
DATE_FORMAT = "%Y-%m-%d"

SECONDS_PER_MINUTE = 60
REFRESH_INTERVAL_MINS_DEFAULT = 15
FLOATING_CAPACITY_LIMIT_NOTIFICATION_OFFSET_MIN = 15

# ATTENTION: the following license logic constants have a dependency with the backend!
# If you change them, the backend needs to be changed as well
EXPIRATION_LICENSE_v1 = "Expiration_v1"
FLOATING_LICENSE_v1 = "Floating_v1"
UNLIMITED_TRIAL_v1 = "UnlimitedTrial_v1"
SINGLE_MACHINE_LICENSE_v1 = "SingleMachine_v1"
TWO_WEEK_TRIAL_LICENSE_v1 = "TwoWeekTrial_v1"


@lru_cache(maxsize=None)
def _is_databricks():
    """Checks if we run inside the databricks runtime"""
    try:
        import psutil

        process_identifier = psutil.Process().parent().cmdline()
        process_identifier_str = ",".join(process_identifier)

        return "databricks" in process_identifier_str
    except:
        return False


class Policy_v1:
    """Base class for license policy. Its instances need to implement the methods below.

    :param data: dict containing license data.
    :param auth: AuthorizationService. Contains e.g. user information.
    """

    def __init__(self, data, auth):
        self.data = data
        self.auth = auth

    def is_valid(self):
        """Check if the license is valid according to the policy."""
        raise NotImplementedError

    def get_validation_error(self):
        """Get the message displayed to the user. Called when license is not valid."""
        raise NotImplementedError


class BackgroundUpdatePolicy_v1(Policy_v1):
    """
    Handles background updates.

    Uses the following license information:

    {
        "key": "EXPP-QC6T-W743-NT4F-ZFC4",
        "license_logic": EXPIRATION_LICENSE_v1,
        "refresh_max_delay_days": 14,
        "refresh_interval_mins": 15,
    }
    """

    def is_valid(self):
        # TODO: enable scenario:
        #   - if the user uses bamboolib after 3 weeks but is offline, license should still work. But then, the offline period should start.
        # TODO: implement the get_validation_error logic if we want to enforce the background updates
        # the error needs to help the user to trigger a refresh
        return True
        # refreshed_at = self.data.get("refreshed_at", None)
        # if refreshed_at is None:
        #     refreshed_at = dt.datetime.now().strftime(DATETIME_FORMAT)
        #     self.data["refreshed_at"] = refreshed_at
        #     self.auth.persist()

        # last_refresh = dt.datetime.strptime(refreshed_at, DATETIME_FORMAT)
        # max_delay = dt.timedelta(days=self.data["refresh_max_delay_days"])
        # now = dt.datetime.now()

        # return now < (last_refresh + max_delay)

    def get_validation_error(self):
        return widgets.HTML("BasePolicy error")


class UserPolicy_v1(Policy_v1):
    """
    Checks if the right user activates the license.

    Uses the following parts of the license object:

    {
        "user_email": "john.doe@gmail.com",
        "user_email_check": True,
    }
    """

    def is_valid(self):
        if self.data["user_email_check"]:
            # This can only fail (return False) during activation of a new license
            # because otherwise, it is always True
            # because auth.get_user_email() is restored from data["user_email"]
            return self.data["user_email"] == self.auth.get_user_email()
        else:
            return True

    def get_validation_error(self):
        email = self.auth.get_user_email()
        message = notification(
            f"Your email address '{email}' is not allowed to use the license with the key '{self.data['key']}'. Please review the email and license",
            type="error",
        )
        log_setup("auth", "UserPolicy_v1", "unauthorized email")
        return activate_license(email=email, _notification_embeddable=message)


class ExpirationPolicy_v1(Policy_v1):
    """
    Checks if the license has expired.

    Uses the following parts of the license object:

    {
        "expiration_date": "2019-12-25",
    }
    """

    def is_valid(self):
        expiration_day = dt.datetime.strptime(self.data["expiration_date"], DATE_FORMAT)
        now = dt.datetime.now()
        return now < (expiration_day + dt.timedelta(days=1))

    def get_validation_error(self):
        outlet = widgets.VBox()
        execute_asynchronously(lambda: self._start_license_validation(outlet))
        return outlet

    def _start_license_validation(self, outlet):
        """
        Get latest license state from server to check if license is still valid. This is a double-check
        when the license on the user's machine is expired.
        It may happen that the user has an old license state on his machine but his license has been
        updated on the server side (e.g. when subscription renewed).
        """
        outlet.children = [notification("Trying to validate your license ...")]

        response = sync_license_with_server(self.data)

        if response.has_error():
            self._show_error_message(outlet, response)
        else:
            license_ = License(response.license, auth)
            if license_.is_valid():
                auth.license = license_
                auth.persist()
                outlet.children = [license_.get_success_embeddable()]
            else:
                self._show_expiration_message(outlet)

    def _show_error_message(self, outlet, response):
        """Show an error message when syncing with server failed."""
        retry_button = Button(
            description="Retry",
            style="primary",
            on_click=lambda _: self._start_license_validation(outlet),
        )

        def activate(button):
            email = self.auth.get_user_email()
            outlet.children = [activate_license(email=email)]

        activation_button = Button(
            description="Activate another license", style="primary", on_click=activate
        )

        outlet.children = [
            notification(
                f"Your license with the key '{self.data['key']}' expired. We tried to double-check your license with our license server but the following error occured:",
                type="error",
            ),
            response.error_embeddable(),
            retry_button,
            widgets.HTML("Alternatively, you can also activate another license:"),
            activation_button,
        ]

    def _show_expiration_message(self, outlet):
        """Show expiration message when license has expired."""
        email = self.auth.get_user_email()
        message = notification(
            f"""Sorry, your license with the key '{self.data['key']}' expired. Please activate another license or <a href='https://bamboolib.com/pricing/' target='_blank'>purchase a new license</a>""",
            type="error",
        )
        log_setup("auth", "ExpirationPolicy_v1", "expired license")
        outlet.children = [
            activate_license(email=email, _notification_embeddable=message)
        ]


class FloatingSeatPolicy_v1(Policy_v1):
    """
    Handles the floating license logic, i.e. if a user is allowed to have/take a floating seat.

    Uses the following elements of a license object:
    {
        "refresh_interval_mins": 15,
        "floating_max_seats": 2,
        "floating_interval_mins": 60,
        "floating_seats": [
            {
                "client_id": "kq2ud8qx09y674b17wca",
                "start_time": "2021-05-18 14:39:10 +0000 UTC",
                "end_time": "2021-05-18 15:39:10 +0000 UTC",
            },
        ],
    }
    """

    def is_valid(self):
        if self._i_currently_have_a_valid_seat():
            if self._i_should_prolong_my_seat():
                execute_asynchronously(self._prolong_my_seat)
            return True
        else:
            return self._try_to_acquire_seat()

    def get_validation_error(self):
        message = notification(
            f"We are sorry but all seats of your floating license {self.data.get('key')} are currently taken. You might want to retry later or you can reach out to your admin to get more seats.",
            type="error",
        )
        log_setup("auth", "FloatingSeatPolicy_v1", "capacity exceeded")
        return message

    def _get_my_seat(self):
        """
        Returns the seat object directly (not a copy of it) or None
        """
        client_id = auth._browser_info.get("bamboolib_client_id")
        seats = self.data["floating_seats"]
        my_seats = [seat for seat in seats if seat.get("client_id") == client_id]
        if len(my_seats) == 0:
            return None
        return my_seats[0]

    def _i_currently_have_a_valid_seat(self):
        my_seat = self._get_my_seat()
        if my_seat is None:
            return False
        utc_now = dt.datetime.now(tz=dt.timezone.utc)
        end_time = dt.datetime.strptime(my_seat["end_time"], DATETIME_FORMAT)
        return end_time > utc_now

    def _i_should_prolong_my_seat(self):
        my_seat = self._get_my_seat()
        utc_now = dt.datetime.now(tz=dt.timezone.utc)
        start_time = dt.datetime.strptime(my_seat["start_time"], DATETIME_FORMAT)
        refresh_min = self.data.get(
            "refresh_interval_mins", REFRESH_INTERVAL_MINS_DEFAULT
        )
        return utc_now > (start_time + dt.timedelta(minutes=refresh_min))

    def _prolong_my_seat(self):
        response = sync_license_with_server(self.data)
        if response.has_error():
            return  # behave as if it worked in order to not disturb the user
        self.data = response.license

        my_seat = self._get_my_seat()
        if my_seat is None:
            return  # it seems like someone deleted this user's valid seat - weird but let's not disturb user
        utc_now = dt.datetime.now(tz=dt.timezone.utc)
        end_time = utc_now + dt.timedelta(minutes=self.data["floating_interval_mins"])
        my_seat["start_time"] = utc_now.strftime(format=DATETIME_FORMAT)
        my_seat["end_time"] = end_time.strftime(format=DATETIME_FORMAT)
        self._save_new_license()

    def _save_new_license(self):
        """Persists a new license file on the machine."""
        response = update_license_on_server(self.data)

        if response.has_error():
            pass  # fail silently for now because this should only be a ConnectionError and this is already logged within the sync function
        else:
            auth.license = License(response.license, auth)
            auth.persist()

    def _remove_outdated_seats(self):
        """The client removes any outdated seats from the license object on the server."""
        seats = self.data["floating_seats"]

        utc_now = dt.datetime.now(tz=dt.timezone.utc)
        valid_seats = []
        for seat in seats:
            if dt.datetime.strptime(seat["end_time"], DATETIME_FORMAT) > utc_now:
                valid_seats.append(seat)
            else:
                pass  # remove seat
        self.data["floating_seats"] = valid_seats

    def _maybe_send_floating_limit_notification(self, got_seat):
        """
        If a user couldn't get a seat, maybe send a notification to our server. Maybe because we don't
        want to spam our server for every failed try.
        """
        seat_got_denied = not got_seat
        too_many_seats = (
            len(self.data["floating_seats"]) > self.data["floating_max_seats"]
        )
        if seat_got_denied or too_many_seats:
            if self.auth.should_send_floating_limit_notification():
                execute_asynchronously(send_floating_limit_notification, self.data)
            else:
                pass

    def _did_acquire_a_seat(self):
        self._remove_outdated_seats()
        seats = self.data["floating_seats"]
        if len(seats) >= self.data["floating_max_seats"]:
            if self.data.get("floating_enforce_limit"):
                return False

        start_time = dt.datetime.now(tz=dt.timezone.utc)
        end_time = start_time + dt.timedelta(
            minutes=self.data["floating_interval_mins"]
        )
        my_seat = {
            "client_id": auth._browser_info.get("bamboolib_client_id"),
            "start_time": start_time.strftime(format=DATETIME_FORMAT),
            "end_time": end_time.strftime(format=DATETIME_FORMAT),
        }
        seats.append(my_seat)
        return True

    def _try_to_acquire_seat(self):
        response = sync_license_with_server(self.data)

        if response.has_error():
            # behave as if it worked in order not to disturb the user
            return True

        self.data = response.license
        success = self._did_acquire_a_seat()
        self._save_new_license()
        self._maybe_send_floating_limit_notification(got_seat=success)
        return success


class SingleMachineBasePolicy_v1(Policy_v1):
    """
    Base class for handling the logic for a license that is tied to a user's machine.

    Uses the following components of a license object:
    {
        "machine_fingerprint": "darwin;;;/Users/johndoe",
        "machine_name": "John Doe's MacBook Pro",
        "activated": False,
        "activation_count": 0,
        "activation_max_count": 5,
    }
    """

    def _get_first_activation_message(self):
        """Return the first activation message."""
        raise NotImplementedError

    def _get_no_remaining_activations_message(self):
        """Return a message when the user has exceeded its activation limit."""
        raise NotImplementedError

    def _get_change_access_message(self, remaining_attempts):
        """
        Inform the user that she is about to transfer a license from one machine to another,
        increasing the number of possible activations.
        """
        raise NotImplementedError

    def _get_activation_count(self):
        """
        Get the number of activations already happened (a license transfer from one machine
        to another counts as an activation).
        """
        ACTIVATION_COUNT_DEFAULT = 0

        count = self.data.get("activation_count", ACTIVATION_COUNT_DEFAULT)
        if count is None:
            return ACTIVATION_COUNT_DEFAULT
        return count

    def _get_activation_max_count(self):
        """Get the maximum allowed number of activations."""
        ACTIVATION_MAX_COUNT_DEFAULT = 5

        max_count = self.data.get("activation_max_count", ACTIVATION_MAX_COUNT_DEFAULT)
        if max_count is None:
            return ACTIVATION_MAX_COUNT_DEFAULT
        return max_count

    def is_valid(self):
        user_path = Path.home()
        os_platform = sys.platform
        fingerprint = f"{os_platform};;;{user_path}"

        return self.data["activated"] and (
            self.data["machine_fingerprint"] == fingerprint
        )

    def get_validation_error(self):
        if self.data["activated"]:
            return self._change_access_to_this_machine()
        else:
            return self._activate_the_first_time()

    def _update_data_during_activation(self):
        self.data["activated"] = True
        user_path = Path.home()
        os_platform = sys.platform
        fingerprint = f"{os_platform};;;{user_path}"
        self.data["machine_fingerprint"] = fingerprint
        self.data["activation_count"] = self._get_activation_count() + 1

        self._after_activation_data_update()

    def _after_activation_data_update(self):
        """Extension point for the TwoWeekTrialPolicy_v1."""
        pass

    def _try_to_activate_license(self, outlet):
        outlet.children = [notification("Trying to activate the license ...")]
        self._update_data_during_activation()

        response = update_license_on_server(self.data)
        if response.has_error():
            retry_button = Button(
                description="Retry",
                style="primary",
                on_click=lambda _: self._try_to_activate_license(outlet),
            )
            outlet.children = [response.error_embeddable(), retry_button]
        else:
            license_ = License(response.license, auth)
            if license_.is_valid():
                auth.license = license_
                auth.persist()
                outlet.children = [license_.get_success_embeddable()]
            else:
                outlet.children = [license_.get_validation_error()]

    def _get_activation_prompt(self, embeddable_message):
        outlet = widgets.VBox()

        activate = Button(
            description="Activate license",
            style="primary",
            on_click=lambda _: self._try_to_activate_license(outlet),
        )

        def cancel(_):
            outlet.children = [activate_license()]

        cancel = Button(description="Cancel", on_click=cancel)

        outlet.children = [embeddable_message, activate, cancel]
        return outlet

    def _activate_the_first_time(self):
        message = notification(self._get_first_activation_message(), type="info")
        return self._get_activation_prompt(message)

    def _change_access_to_this_machine(self):
        remaining_attempts = (
            self._get_activation_max_count() - self._get_activation_count()
        )

        if remaining_attempts < 1:
            message = notification(
                self._get_no_remaining_activations_message(), type="error"
            )
            email = self.auth.get_user_email()
            log_setup("auth", self, "no remaining transfers left")
            return activate_license(email=email, _notification_embeddable=message)
        else:
            message = notification(
                self._get_change_access_message(remaining_attempts), type="info"
            )
            log_setup("auth", self, "show transfer option")
            return self._get_activation_prompt(message)


class SingleMachinePolicy_v1(SingleMachineBasePolicy_v1):
    """Handles a single user license."""

    def _get_first_activation_message(self):
        return f"This license can only be used on a single machine. Do you want to activate the license on this machine?"

    def _get_no_remaining_activations_message(self):
        return f"""The license with the key '{self.data['key']}' can only be used on a single machine. The license can be transferred to another computer but currently, there are no remaining transfers left. Please activate another license or <a href='https://bamboolib.com/pricing/' target='_blank'>purchase a new license</a>. If you want to regularly switch access between computers, please consider a floating license. If you need help, please contact us via <a href="mailto:support+single_machine_no_transfers_left@8080labs.com?subject=Single Machine license has no transfers left" target="_blank">support@8080labs.com</a>"""

    def _get_change_access_message(self, remaining_attempts):
        return f"The license with the key '{self.data['key']}' can only be used on a single machine but it is currently used on another machine. If you want, you can transfer the license to this computer. If you transfer the license, the other computer will lose access and your remaining transfers will decrease. Currently, you have {remaining_attempts} remaining transfer(s) left."


class TwoWeekTrialPolicy_v1(SingleMachineBasePolicy_v1):
    """Handles a two week trial license."""

    def _get_first_activation_message(self):
        return f"The trial license is valid for 14 days after activation. Do you want to start your trial now?"

    def _get_no_remaining_activations_message(self):
        return f"""The trial license with the key '{self.data['key']}' can only be used on a single machine. The license can be transferred to another computer but currently, there are no remaining transfers left. Please activate another license or <a href='https://bamboolib.com/pricing/' target='_blank'>purchase a new license</a>. If you want to regularly switch access between computers, please consider a floating license. If you need help, please contact us via <a href="mailto:support+single_machine_no_transfers_left@8080labs.com?subject=Single Machine license has no transfers left" target="_blank">support@8080labs.com</a>"""

    def _get_change_access_message(self, remaining_attempts):
        return f"The trial license with the key '{self.data['key']}' can only be used on a single machine but it is currently used on another machine. If you want, you can transfer the trial license to this computer. If you transfer the license, the other computer will lose access and your remaining transfers will decrease. Currently, you have {remaining_attempts} remaining transfer(s) left."

    def _after_activation_data_update(self):
        expiration_date = dt.datetime.now() + dt.timedelta(days=14)
        self.data["expiration_date"] = dt.datetime.strftime(
            expiration_date, DATE_FORMAT
        )


class UnimplementedLicensePolicy_v1(Policy_v1):
    """Handles the case the bamboolib client doesn't support the license type on the server."""

    def is_valid(self):
        return False

    def get_validation_error(self):
        return notification(
            "The current bamboolib version is outdated and does not support the license that you want to activate. Please upgrade bamboolib to the newest version. If you still see the error after upgrading bamboolib please contact us via support@8080labs.com",
            type="error",
        )


class License:
    """
    License object. Handles the policies for the respective license logic (e.g. floating, single user)

    :param data: dict containing data about the license.
    :param auth: AuthorizationService. Contains e.g. information about the user.
    """

    def __init__(self, data, auth):
        self.data = data
        self.auth = auth

        schema = data.get("license_logic", None)
        if schema in [EXPIRATION_LICENSE_v1, UNLIMITED_TRIAL_v1]:
            policies = [UserPolicy_v1, ExpirationPolicy_v1, BackgroundUpdatePolicy_v1]
        elif schema == FLOATING_LICENSE_v1:
            policies = [
                FloatingSeatPolicy_v1,
                UserPolicy_v1,
                ExpirationPolicy_v1,
                BackgroundUpdatePolicy_v1,
            ]
        elif schema == SINGLE_MACHINE_LICENSE_v1:
            policies = [
                SingleMachinePolicy_v1,
                UserPolicy_v1,
                ExpirationPolicy_v1,
                BackgroundUpdatePolicy_v1,
            ]
        elif schema == TWO_WEEK_TRIAL_LICENSE_v1:
            policies = [
                TwoWeekTrialPolicy_v1,  # enforces activation and single machine
                UserPolicy_v1,
                ExpirationPolicy_v1,
                BackgroundUpdatePolicy_v1,
            ]
        else:
            try:
                log_error("catched error", self, "license type is not supported")
            except:
                # during init log_error might throw a circular dependency error
                pass
            policies = [UnimplementedLicensePolicy_v1]

        self.policies = [policy(data, auth) for policy in policies]

    def get_data(self):
        return self.data

    def get_key(self):
        """Get the license key."""
        return self.data["key"]

    def get_type(self):
        """Get the license type, e.g. trial, paid, or other"""
        schema = self.data.get("license_logic", None)
        subscription = self.data.get("paddle_subscription_id", None)

        if schema in [TWO_WEEK_TRIAL_LICENSE_v1]:
            return "trial"
        elif schema in [UNLIMITED_TRIAL_v1]:
            return "unlimited trial"
        elif subscription is not None:
            # should be checked last because there might be other reasons why we inserted something there
            return "paid"
        else:
            # might be a normal license that we gave out for free
            return "other"

    def get_logic(self):
        """Get license logic, e.g. Floating_v1"""
        return self.data.get("license_logic", "None")

    def get_refresh_seconds(self):
        try:
            refresh_mins = self.data["refresh_interval_mins"]
        except:
            refresh_mins = REFRESH_INTERVAL_MINS_DEFAULT
        return refresh_mins * SECONDS_PER_MINUTE

    def permit_continuous_license_updates(self):
        """If we have a floating license, need to make background updates."""
        if any(type(policy) is FloatingSeatPolicy_v1 for policy in self.policies):
            # continuous updates might interfere with the updates as part of the floating policy, thus we do not permit them
            return False
        else:
            return True

    # TODO: rename to get_authorization_error?
    def get_validation_error(self):
        for policy in self.policies:
            if policy.is_valid():
                pass
            else:
                return policy.get_validation_error()

    # TODO: rename to is_authorized?
    def is_valid(self):
        return all([policy.is_valid() for policy in self.policies])

    def get_success_embeddable(self):
        """Return message if activation has been successful."""
        log_setup("auth", "ActivationView", "activation success")
        message = """
Thank you for activating your license!<br>
Please execute your Jupyter cell again in order to see the bamboolib widget.
Have a great day!
"""
        return notification(message, "success")

    def get_license_user_info(self):
        """Maybe inform user about the state of her license, e.g. when it is about to expire."""
        schema = self.data.get("license_logic", None)

        if schema == TWO_WEEK_TRIAL_LICENSE_v1:
            remaining_days = self._get_remaining_trial_days()
            if remaining_days == 0:
                return notification(f"Your trial expires tonight", type="warning")
            elif remaining_days < 3:
                return notification(
                    f"Your trial expires in {remaining_days} day(s). It’s the perfect time to upgrade! Buy your license key <a href='https://bamboolib.8080labs.com/pricing/' target='_blank'>here</a>.",
                    type="info",
                )
            elif remaining_days < 7:
                return notification(
                    f"Your trial expires in {remaining_days} day(s). If you want to upgrade you can buy a license key <a href='https://bamboolib.8080labs.com/pricing/' target='_blank'>here</a>.",
                    type="info",
                )

        return widgets.HTML()

    def _get_remaining_trial_days(self):
        # if license expires on Tue
        # 0 during Tue
        # 1 during Mon
        expiration_date = dt.datetime.strptime(
            self.data["expiration_date"], DATE_FORMAT
        )
        today = dt.datetime.today()
        return (expiration_date - today).days + 1


class User:
    """
    A user object.

    :param data: dict containing data about the license.
    :param auth: AuthorizationService. Contains e.g. information about the user.

    Data used:
    {
        "schema": "User_v1",
        "email": "john.doe@gmail.com",
    }
    """

    def __init__(self, data, auth):
        self.data = data
        self.auth = auth

    def get_data(self):
        return self.data

    def get_email(self):
        return self.data["email"]


class CredentialsStorage:
    """
    Manages storage of the license object on a user's machine, including encryption/decryption.

    :param auth_service: AuthorizationService.
    """

    def __init__(self, auth_service):
        self.auth_service = auth_service
        self._public_credentials_file = BAMBOOLIB_LIBRARY_CONFIG_PATH / "LICENSE"
        self._internal_credentials_file = (
            BAMBOOLIB_LIBRARY_INTERNAL_CONFIG_PATH / "ek261"
        )
        self.f = None  # Fernet key

        self._setup_fernet()
        # Hint: don't start any continous background processes/threads here
        # because then the extension installation does not terminate any more
        # because this method is run during normal bamboolib import
        # which is run during installation of the extension
        # and if there is a thread, then the extension installation won't terminate
        # Exception: daemon threads should work, though, because they are terminated
        # when their main thread terminates

    def _setup_fernet(self):
        """Set up the encryptor/decryptor."""
        password_str = "hzuHQGU&67"
        password_bytes = password_str.encode()  # convert to type bytes
        salt_bytes = b"SkeX9LRyE0!F_HfV/HQKc7xkFiQ#Db22Zs+11aSqjRO-Rl2j0="  # must be of type bytes

        kdf = PBKDF2HMAC(
            algorithm=hashes.SHA256(),
            length=32,
            salt=salt_bytes,
            iterations=100000,
            backend=default_backend(),
        )
        key = base64.urlsafe_b64encode(
            kdf.derive(password_bytes)
        )  # Can only use kdf once

        # encryptor / decryptor
        self.f = Fernet(key)

    def _file_exists(self, file):
        return file.exists() and file.is_file()

    def _delete_file(self, file):
        file.unlink()

    def _write_to_file(self, file, encrypted_bytes):
        with open(file, "wb") as file:
            file.write(encrypted_bytes)

    def _maybe_create_credential_folders(self):
        BAMBOOLIB_LIBRARY_CONFIG_PATH.mkdir(parents=True, exist_ok=True)
        BAMBOOLIB_LIBRARY_INTERNAL_CONFIG_PATH.mkdir(parents=True, exist_ok=True)

    def maybe_restore(self):
        # when in doubt then the public file overwrites the internal file because
        # we want to be able to give users new public files without manipulating our internal files
        self._maybe_restore_credentials_from_file(self._public_credentials_file)
        self._maybe_restore_credentials_from_file(self._internal_credentials_file)

    def _maybe_restore_credentials_from_file(self, file):
        if not self._file_exists(file):
            return

        with open(file, "rb") as file:
            encrypted_bytes = file.read()
            try:
                decrypted_bytes = self.f.decrypt(encrypted_bytes)
                credentials = json.loads(decrypted_bytes.decode())
            except:
                # silently fail if the decryption did fail eg due to a wrong file
                credentials = None

        if not self._credentials_format_is_valid(credentials):
            return

        auth_service = self.auth_service
        auth_service.license = License(credentials["license"], auth_service)
        auth_service.user = User(credentials["user"], auth_service)

        # make sure that valid information is duplicated
        self._update_credentials_files(encrypted_bytes)

    def _update_credentials_files(self, encrypted_bytes):
        self._maybe_create_credential_folders()

        for file in [self._internal_credentials_file, self._public_credentials_file]:
            try:
                if self._file_exists(file):
                    self._delete_file(file)

                self._write_to_file(file, encrypted_bytes)
            except:
                pass

    def _credentials_format_is_valid(self, credentials):
        if credentials is None:
            return False
        return credentials["license"] is not None

    def persist(self, string):
        # TODO: only persist if the credentials storage is not already the same
        encrypted_bytes = self.f.encrypt(string.encode())
        self._update_credentials_files(encrypted_bytes)


class AuthorizationService:
    """
    Handles parts of the authorization process, e.g. deciding if user can use bamboolib for free.
    """

    def __init__(self):
        self.license = None
        self.user = None
        self.runs_background_updates = False
        self.credentials_storage = CredentialsStorage(self)

        self._browser_info = {}
        self._sent_last_floating_notification = dt.datetime(year=1980, month=1, day=1)

        # This will try to update self.license and self.user
        self.credentials_storage.maybe_restore()

        # Hint: don't start any continous background processes/threads here
        # because then the extension installation does not terminate any more
        # because this method is run during normal bamboolib import
        # which is run during installation of the extension
        # and if there is a thread, then the extension installation won't terminate
        # Exception: daemon threads should work, though, because they are terminated
        # when their main thread terminates

    def get_user_email(self):
        if self.user is None:
            if self._is_kaggle_kernel():
                return KAGGLE_KERNEL_ANONYMOUS
            elif self._is_binder_notebook():
                return BINDER_NOTEBOOK_ANONYMOUS
            else:
                return NO_USER_EMAIL
        else:
            return self.user.get_email()

    def get_license_key(self):
        if self.license is None:
            return "NO_LICENSE_KEY"
        else:
            return self.license.get_key()

    def get_license_type(self):
        if self.license is None:
            return "None"
        else:
            return self.license.get_type()

    def get_license_logic(self):
        if self.license is None:
            return "None"
        else:
            return self.license.get_logic()

    def set_browser_info(self, browser_info):
        self._browser_info = browser_info

    def should_send_floating_limit_notification(self):
        """Decide if we should send a floating limit notification to our server."""
        now = dt.datetime.now()
        delta = FLOATING_CAPACITY_LIMIT_NOTIFICATION_OFFSET_MIN
        should_resend = now > (
            self._sent_last_floating_notification + dt.timedelta(minutes=delta)
        )
        if should_resend:
            self._sent_last_floating_notification = now
        return should_resend

    def _is_free_user(self) -> bool:
        """Returns True if the user may use bamboolib for free."""
        whitelist = [
            self.is_databricks(),
            self._is_binder_notebook(),
            self._is_kaggle_kernel(),
        ]
        if any(whitelist):
            return True

        blacklist = [self._is_jupyterhub()]
        if any(blacklist):
            return False

        if self._browser_info.get("window.location.hostname") in [
            "localhost",
            "127.0.0.1",
            "0.0.0.0",
        ]:
            return True

        return False

    def _is_jupyterhub(self) -> bool:
        try:
            import psutil

            process_identifier = psutil.Process().parent().cmdline()
            process_identifier_str = ",".join(process_identifier)

            return "jupyterhub" in process_identifier_str
        except:
            return False

    def _is_kaggle_kernel(self) -> bool:
        try:
            import psutil

            process_identifier = psutil.Process().parent().cmdline()
            process_identifier_str = ",".join(process_identifier)

            has_kaggle_folder = "/kaggle/working" in process_identifier_str
            uses_conda = "/opt/conda/bin/python" in process_identifier_str

            return has_kaggle_folder and uses_conda
        except:
            return False

    def _is_binder_notebook(self) -> bool:
        # real_example_0 = "--NotebookApp.base_url=/user/8080labs-bamboo-r_demo_notebook-64n8n1dy/"
        # real_example_1 = "--NotebookApp.base_url=/user/binder-examples-jupyterlab-3k5mlxo1/"
        # longer_slug_example = "--NotebookApp.base_url=/user/binder-examples-jupyterlab-3k5mlxo1xxxx/"
        # wrong_example = "--NotebookApp.base_url=/user/binder-examples-jupyterlab-3k5/"

        def is_binder_identifier(string):
            try:
                import re

                search = re.search(
                    "^--NotebookApp.base_url=(?:.*)-[a-zA-Z0-9]{4,}\/$", string
                )
                return bool(search.group())
            except:
                return False

        try:
            import psutil

            process_identifier = psutil.Process().parent().cmdline()
            return any(
                [is_binder_identifier(identifier) for identifier in process_identifier]
            )
        except:
            return False

    def is_databricks(self):
        # Explanation: used a separate method because of the caching.
        # Flo was unsure if some adjustment is needed when caching instance methods
        # Can be followed up on later
        return _is_databricks()

    def _get_existing_license_error(self):
        if self.license.is_valid():
            return None
        else:
            return self.license.get_validation_error()

    def _get_license_error(self):
        if self.license is None:
            return activate_license()
        else:
            return self._get_existing_license_error()

    def get_license_user_info(self):
        if self.license is None:
            return widgets.HTML()
        else:
            return self.license.get_license_user_info()

    def get_authorization_error(self):
        if self._is_free_user():
            return None

        self.maybe_start_async_license_updates()

        return self._get_license_error()

    def has_unlimited_plugins(self):
        """Returns True if the user may use bamboolib plugins."""
        # always allow plugins for now (Jan 11 2022) in order to not have any troubles
        # we might revisit this later if we want to add license constraints again
        return True
        # ## old logic
        # if self._is_free_user():
        #     return True
        # if self.license is None:
        #     return False
        # else:
        #     return True

    def maybe_start_async_license_updates(self):
        """Keep local and server license in sync using a background thread."""
        if env.TESTING_MODE or config.is_in_confidential_mode():
            return  # dont start license updates

        if self.runs_background_updates:
            pass  # dont start another background update thread
        else:
            self.runs_background_updates = True
            execute_asynchronously(
                lambda: self._maybe_perform_continuous_license_updates()
            )

    def _maybe_perform_continuous_license_updates(self):
        """Continously keep the local license version in sync with the server version."""
        while self.license is not None:
            if not self.license.permit_continuous_license_updates():
                break

            response = sync_license_with_server(self.license.get_data())
            if response.has_error():
                pass  # try again later
            else:
                self.license = License(response.license, self)
                self.persist()

            time.sleep(self.license.get_refresh_seconds())

        # when loop breaks
        self.runs_background_updates = False

    def activate(self, user_email, key):
        """Activate license."""
        response = get_license_from_server(user_email, key)
        if response.has_error():
            return activate_license(
                email=user_email,
                key=key,
                _notification_embeddable=response.error_embeddable(),
            )

        self.license = License(response.license, self)
        # the user data needs to be set before license.is_valid()
        # because the UserPolicy_v1 asks the auth for the current_user_email
        user_data = {"email": user_email, "schema": "User_v1"}
        self.user = User(user_data, self)

        if not self.license.is_valid():
            return self.license.get_validation_error()

        self.persist()
        maybe_identify_segment(user_email, key)
        self.maybe_start_async_license_updates()
        return self.license.get_success_embeddable()

    def _get_data(self, attribute):
        if attribute is None:
            return None
        else:
            return attribute.get_data()

    def persist(self):
        credentials = json.dumps(
            {
                "schema": "Credentials_v0",
                "license": self._get_data(self.license),
                "user": self._get_data(self.user),
            }
        )
        self.credentials_storage.persist(credentials)

    def set_license(self, encrypted_string):
        encrypted_bytes = encrypted_string.encode()
        self.credentials_storage._update_credentials_files(encrypted_bytes)
        self.credentials_storage.maybe_restore()


auth = AuthorizationService()
