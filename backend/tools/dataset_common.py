"""Compatibility imports for tools written before the common package was split."""

from backend.tools.common import *  # noqa: F403
from backend.tools.common.transfer import transfer_file


def copy_with_conflict(source, target, context):  # type: ignore[no-untyped-def]
    return transfer_file(source, target, context, mode="copy")
