# -*- coding: utf-8 -*-
"""
apikey util.
"""

import getpass
import sys

from six.moves import input
import wandb
from wandb.apis import InternalApi
from wandb.errors.term import LOG_STRING
from wandb.util import isatty, write_netrc


LOGIN_CHOICE_ANON = "Private W&B dashboard, no account required"
LOGIN_CHOICE_NEW = "Create a W&B account"
LOGIN_CHOICE_EXISTS = "Use an existing W&B account"
LOGIN_CHOICE_DRYRUN = "Don't visualize my results"
LOGIN_CHOICES = [
    LOGIN_CHOICE_ANON,
    LOGIN_CHOICE_NEW,
    LOGIN_CHOICE_EXISTS,
    LOGIN_CHOICE_DRYRUN,
]


def prompt_api_key(
    settings,
    api=None,
    input_callback=None,
    browser_callback=None,
    no_offline=False,
    local=False,
):
    input_callback = input_callback or getpass.getpass
    api = api or InternalApi()
    anon_mode = settings.anonymous or "never"
    jupyter = settings.jupyter or False
    app_url = settings.base_url.replace("//api.", "//app.")

    choices = [choice for choice in LOGIN_CHOICES]
    if anon_mode == "never":
        # Omit LOGIN_CHOICE_ANON as a choice if the env var is set to never
        choices.remove(LOGIN_CHOICE_ANON)
    if jupyter or no_offline:
        choices.remove(LOGIN_CHOICE_DRYRUN)

    if anon_mode == "must":
        result = LOGIN_CHOICE_ANON
    # If we're not in an interactive environment, default to dry-run.
    elif not isatty(sys.stdout) or not isatty(sys.stdin):
        result = LOGIN_CHOICE_DRYRUN
    elif local:
        result = LOGIN_CHOICE_EXISTS
    else:
        for i, choice in enumerate(choices):
            wandb.termlog("(%i) %s" % (i + 1, choice))

        def prompt_choice():
            try:
                return (
                    int(
                        input(
                            "%s: Enter your choice: " % LOG_STRING
                        )
                    )
                    - 1  # noqa: W503
                )
            except ValueError:
                return -1

        idx = -1
        while idx < 0 or idx > len(choices) - 1:
            idx = prompt_choice()
            if idx < 0 or idx > len(choices) - 1:
                wandb.termwarn("Invalid choice")
        result = choices[idx]
        wandb.termlog("You chose '%s'" % result)

    if result == LOGIN_CHOICE_ANON:
        key = api.create_anonymous_api_key()

        write_key(settings, key)
        return key
    elif result == LOGIN_CHOICE_NEW:
        key = browser_callback(signup=True) if browser_callback else None

        if not key:
            wandb.termlog(
                "Create an account here: {}/authorize?signup=true".format(app_url)
            )
            key = input_callback(
                "%s: Paste an API key from your profile and hit enter"
                % LOG_STRING
            ).strip()

        write_key(settings, key)
        return key
    elif result == LOGIN_CHOICE_EXISTS:
        key = browser_callback() if browser_callback else None

        if not key:
            wandb.termlog(
                "You can find your API key in your browser here: {}/authorize".format(
                    app_url
                )
            )
            key = input_callback(
                "%s: Paste an API key from your profile and hit enter"
                % LOG_STRING
            ).strip()
        write_key(settings, key)
        return key
    else:
        # Jupyter environments don't have a tty, but we can still try logging in using
        # the browser callback if one is supplied.
        key, anonymous = (
            browser_callback()
            if jupyter and browser_callback
            else (None, False)
        )

        write_key(settings, key)
        return key


def write_key(settings, key):
    if not key:
        return

    # Normal API keys are 40-character hex strings. Onprem API keys have a
    # variable-length prefix, a dash, then the 40-char string.
    prefix, suffix = key.split("-") if "-" in key else ("", key)

    if len(suffix) == 40:
        write_netrc(settings.base_url, "user", key)
        return
    raise ValueError("API key must be 40 characters long, yours was %s" % len(key))
