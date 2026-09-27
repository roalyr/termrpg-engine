"""Terminal text styles (§6.1): bold, dim, inverse and a single orange accent.

Orange is reserved for danger and exposure warnings so it keeps its meaning.
Every function returns plain text when styles are disabled (/color off).
"""
RESET = "\033[0m"
BOLD = "\033[1m"
DIM = "\033[2m"
INVERSE = "\033[7m"
ORANGE = "\033[38;5;208m"


def _wrap(text: str, codes: str, enabled: bool) -> str:
    if not enabled or not text:
        return text
    return f"{codes}{text}{RESET}"


def bold(text: str, enabled: bool = True) -> str:
    return _wrap(text, BOLD, enabled)


def dim(text: str, enabled: bool = True) -> str:
    return _wrap(text, DIM, enabled)


def inverse(text: str, enabled: bool = True) -> str:
    return _wrap(text, INVERSE, enabled)


def accent(text: str, enabled: bool = True) -> str:
    """Orange bold: danger and warnings."""
    return _wrap(text, ORANGE + BOLD, enabled)


def alarm(text: str, enabled: bool = True) -> str:
    """Orange inverse: the DANGER status badge."""
    return _wrap(text, ORANGE + INVERSE + BOLD, enabled)
