from core.menu import menu_for, menu_text


def menu_line(state) -> str:
    """The proximity menu as one plain line (title, options and hint), or '' on empty floor."""
    menu = menu_for(state)
    return f"{menu_text(menu)} {menu.hint}".strip() if menu else ""
