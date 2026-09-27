"""Small wrapper around clc99's Metasploit-style output."""

from clc99 import print_error, print_good, print_status, print_warning


def status(message: str) -> None:
    print_status(message)


def good(message: str) -> None:
    print_good(message)


def warning(message: str) -> None:
    print_warning(message)


def error(message: str) -> None:
    print_error(message)
