DEFAULT_TIMEOUT = 10

_timeout = DEFAULT_TIMEOUT


def set_timeout(timeout: float) -> None:
    global _timeout
    _timeout = timeout


def get_timeout() -> float:
    return _timeout
