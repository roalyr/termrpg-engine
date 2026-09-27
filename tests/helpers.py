from core.menu import menu_for, menu_text


def menu_line(state) -> str:
    """The proximity menu as one plain line (title, options and hint), or '' on empty floor."""
    menu = menu_for(state)
    return f"{menu_text(menu)} {menu.hint}".strip() if menu else ""


def find(state, entity_id):
    """(node_id, row, col) of a placed fixture or actor."""
    for node in state.nodes.values():
        for p in node.placements:
            if p.entity_id == entity_id:
                return node.id, p.row, p.col
    raise KeyError(entity_id)


def on(state, entity_id):
    """Puts the player on an entity's tile with the proximity menu open."""
    node_id, row, col = find(state, entity_id)
    return state._replace(current_node_id=node_id, player_row=row, player_col=col, proximity_menu_active=True)


def walk_to(state, entity_id):
    """Walks with WASD from the current tile to an entity in the same room; returns the final state."""
    from core.actions import dispatch_action
    node_id, row, col = find(state, entity_id)
    assert node_id == state.current_node_id, f"{entity_id} is not in {state.current_node_id}"
    last = state.nodes[node_id].size - 1
    inner_r, inner_c = min(max(row, 1), last - 1), min(max(col, 1), last - 1)
    for target_r, target_c in ((inner_r, state.player_col), (inner_r, inner_c), (row, col)):
        while state.player_row != target_r:
            state = dispatch_action(state, "s" if target_r > state.player_row else "w")
        while state.player_col != target_c:
            state = dispatch_action(state, "d" if target_c > state.player_col else "a")
    return state
