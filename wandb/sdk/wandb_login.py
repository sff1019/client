#
# -*- coding: utf-8 -*-
"""
Log in to Weights & Biases, authenticating your machine to log data to your
account.
"""

from __future__ import print_function

import click
import wandb
from wandb.errors.error import UsageError

from .internal.internal_api import Api
from .lib import apikey
from .wandb_settings import Settings

if wandb.TYPE_CHECKING:  # type: ignore
    from typing import Dict, Optional  # noqa: F401 pylint: disable=unused-import


def login(anonymous=None, key=None, relogin=None, host=None, force=None):
    """Log in to W&B.

    Arguments:
        anonymous (string, optional): Can be "must", "allow", or "never".
            If set to "must" we'll always login anonymously, if set to
            "allow" we'll only create an anonymous user if the user
            isn't already logged in.
        key (string, optional): authentication key.
        relogin (bool, optional): If true, will re-prompt for API key.
        host (string, optional): The host to connect to.

    Returns:
        bool: if key is configured

    Raises:
        UsageError - if api_key can not configured and no tty
    """
    kwargs = dict(locals())
    configured = _login(**kwargs)
    return True if configured else False


class _WandbLogin(object):
    def __init__(self):
        self.kwargs: Optional[Dict] = None
        self._settings: Optional[Settings] = None
        self._backend = None
        self._silent = None
        self._wl = None
        self._key = None

    def setup(self, kwargs):
        self.kwargs = kwargs

        # built up login settings
        login_settings: Settings = wandb.Settings()
        settings_param = kwargs.pop("_settings", None)
        if settings_param:
            login_settings._apply_settings(settings_param)
        _logger = wandb.setup()._get_logger()
        login_settings._apply_login(kwargs, _logger=_logger)

        # make sure they are applied globally
        self._wl = wandb.setup(settings=login_settings)
        self._settings = self._wl._settings

    def is_apikey_configured(self):
        return apikey.api_key(settings=self._settings) is not None

    def set_backend(self, backend):
        self._backend = backend

    def set_silent(self, silent):
        self._silent = silent

    def login(self):
        apikey_configured = self.is_apikey_configured()
        if self._settings.relogin:
            apikey_configured = False
        if not apikey_configured:
            return False

        if not self._silent:
            self.login_display()

        return apikey_configured

    def login_display(self):
        # check to see if we got an entity from the setup call
        active_entity = self._wl._get_entity()
        login_info_str = "(use `wandb login --relogin` to force relogin)"
        if active_entity:
            login_state_str = "Currently logged in as:"
            wandb.termlog(
                "{} {} {}".format(
                    login_state_str,
                    click.style(active_entity, fg="yellow"),
                    login_info_str,
                ),
                repeat=False,
            )
        else:
            login_state_str = "W&B API key is configured"
            wandb.termlog(
                "{} {}".format(login_state_str, login_info_str,), repeat=False,
            )

    def configure_api_key(self, key):
        if self._settings._jupyter and not self._settings._silent:
            wandb.termwarn(
                (
                    "If you're specifying your api key in code, ensure this "
                    "code is not shared publically.\nConsider setting the "
                    "WANDB_API_KEY environment variable, or running "
                    "`wandb login` from the command line."
                )
            )
        apikey.write_key(self._settings, key)
        self.update_session(key)
        self._key = key

    def update_session(self, key):
        _logger = wandb.setup()._get_logger()
        settings: Settings = wandb.Settings()
        login_settings = dict(api_key=key) if key else dict(mode="offline")
        settings._apply_source_login(login_settings, _logger=_logger)
        self._wl._update(settings=settings)
        # Whenever the key changes, make sure to pull in user settings
        # from server.
        if not self._wl.settings._offline:
            self._wl._update_user_settings()

    def prompt_api_key(self):
        api = Api(self._settings)
        key = apikey.prompt_api_key(
            self._settings,
            api=api,
            no_offline=self._settings.force,
            no_create=self._settings.force,
        )
        if key is False:
            raise UsageError("api_key not configured (no-tty).  Run wandb login")
        self.update_session(key)
        self._key = key

    def propogate_login(self):
        # TODO(jhr): figure out if this is really necessary
        if self._backend:
            # TODO: calling this twice is gross, this deserves a refactor
            # Make sure our backend picks up the new creds
            # _ = self._backend.interface.communicate_login(key, anonymous)
            pass


def _login(
    anonymous=None,
    key=None,
    relogin=None,
    host=None,
    force=None,
    _backend=None,
    _silent=None,
    _disable_warning=None,
):
    kwargs = dict(locals())
    _disable_warning = kwargs.pop("_disable_warning", None)

    if wandb.run is not None:
        if not _disable_warning:
            wandb.termwarn("Calling wandb.login() after wandb.init() has no effect.")
        return True

    wlogin = _WandbLogin()

    _backend = kwargs.pop("_backend", None)
    if _backend:
        wlogin.set_backend(_backend)

    _silent = kwargs.pop("_silent", None)
    if _silent:
        wlogin.set_silent(_silent)

    # configure login object
    wlogin.setup(kwargs)

    if wlogin._settings._offline:
        return False

    # perform a login
    logged_in = wlogin.login()

    key = kwargs.get("key")
    if key:
        wlogin.configure_api_key(key)

    if logged_in:
        return logged_in

    if not key:
        wlogin.prompt_api_key()

    # make sure login credentials get to the backend
    wlogin.propogate_login()

    return wlogin._key or False
