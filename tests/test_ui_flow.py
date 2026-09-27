"""UI and UX: event ordering, one-time warnings, plain wording, menu hints, styles and layout."""
import re
import unittest

from core.actions import dispatch_action
from core.persistence import state_from_dict, state_to_dict
from core.presets import init_game_state, DEFAULT_DATA_DIR
from core.reducers import ALL_ITEMS_BY_ID
from core.text import danger, gain, speech
from core.tick import process_tick
from core.types import Exposure
from tests.helpers import menu_line
from ui import style
from ui.render import render_frame
from ui.text_tools import visible_len

RAW_ID = re.compile(r"\b[a-z]+_[a-z_]+\b")  # e.g. seal_fitting, vent_duct


def new(anchor=1, routine=1):
    return init_game_state(DEFAULT_DATA_DIR, "Tester", anchor, routine)


def at(state, node_id, row, col):
    return state._replace(current_node_id=node_id, player_row=row, player_col=col, proximity_menu_active=True)


def plain(state, width=40, height=None):
    return render_frame(state._replace(color_enabled=False), width, terminal_height=height)


class TestZone5(unittest.TestCase):
    def test_events_sorted_danger_then_gains_then_rest(self):
        s = new()._replace(message_buffer=(speech("Radek", "Hi."), "You wait.", gain("Skill: Teamwork."),
                                           danger("Cold 11.0 of 15.")))
        frame = plain(s)
        order = [frame.index(t) for t in ("! Cold", "+ Skill", "You wait", 'Radek: "Hi."')]
        self.assertEqual(order, sorted(order))
        self.assertNotIn("~ ", frame)

    def test_warning_fires_once_per_level(self):
        s = new()._replace(current_node_id="stn_a_sub",
                           character=new().character._replace(exposure=Exposure(4.9, 0, 4.8)))
        s1 = process_tick(s._replace(message_buffer=()), "")
        self.assertTrue(any(m.startswith("!! ") for m in s1.message_buffer))
        s2 = process_tick(s1._replace(message_buffer=()), "")
        self.assertFalse(any(m.startswith("!! ") for m in s2.message_buffer))

    def test_recovery_is_announced(self):
        s = new()._replace(character=new().character._replace(exposure=Exposure(5.5, 0, 0)))
        s1 = process_tick(s._replace(message_buffer=()), "")
        self.assertIn("You're breathing easier.", s1.message_buffer)

    def test_player_text_has_no_raw_ids(self):
        s = at(new(1, 2), "stn_b_dock", 4, 4)._replace(character=new(1, 2).character._replace(inventory=()))
        for cmd in ("f", "/inspect freight_crate", "/talk npc_tarek", "/barter npc_tarek", "/help"):
            out = dispatch_action(s, cmd)
            for m in out.message_buffer:
                self.assertIsNone(RAW_ID.search(m), f"{cmd}: {m}")

    def test_sealed_container_says_what_it_needs(self):
        s = at(new(1, 2), "stn_b_dock", 4, 4)._replace(character=new(1, 2).character._replace(inventory=()))
        self.assertIn("Needs a pry-bar or a strong lifter.", menu_line(s))

    def test_room_description_only_on_first_visit(self):
        s = at(new(), "stn_a_bunkroom", 0, 2)
        first = dispatch_action(s, "g")
        self.assertTrue(any(m.startswith("~ Open transfer bay") for m in first.message_buffer))
        back = dispatch_action(at(first, "stn_a_berth", 0, 3), "g")
        again = dispatch_action(at(back, "stn_a_bunkroom", 0, 2), "g")
        self.assertFalse(any(m.startswith("~ Open transfer bay") for m in again.message_buffer))

    def test_arriving_somewhere_hostile_warns(self):
        s = at(new(), "stn_a_bunkroom", 4, 2)
        s = dispatch_action(s, "u")
        s = dispatch_action(s, "g")
        self.assertTrue(any(m.startswith("!! Thin air, cold") for m in s.message_buffer))


class TestMenu(unittest.TestCase):
    def test_menu_lists_only_real_choices(self):
        line = menu_line(at(new(), "stn_a_bunkroom", 1, 3))
        self.assertEqual(line, "Crew Locker: F search")

    def test_go_option_names_the_hazard(self):
        s = at(new(3, 3), "stn_a_berth", 5, 3)
        s = dispatch_action(s, "u")
        self.assertIn("G go to Sub-Deck (thin air, cold)", menu_line(s))

    def test_use_option_names_the_source(self):
        self.assertIn("U open (Seam Scraper training)", menu_line(at(new(1, 1), "stn_a_bunkroom", 4, 2)))
        s = at(new(2, 2), "stn_a_bunkroom", 4, 2)._replace(character=new(2, 2).character._replace(inventory=()))
        self.assertIn("Needs a pipe fitting or a spanner.", menu_line(s))

    def test_menu_is_not_in_the_message_buffer(self):
        s = dispatch_action(at(new(), "stn_a_bunkroom", 1, 2), "d")
        self.assertTrue(s.proximity_menu_active)
        self.assertFalse(any("search" in m for m in s.message_buffer))
        self.assertIn("F search", plain(s))


class TestFrame(unittest.TestCase):
    def test_styles_on_and_off(self):
        s = new()._replace(message_buffer=(danger("Cold 11.0 of 15."), gain("Skill: Teamwork.")))
        styled = render_frame(s, 40)
        self.assertIn(style.ORANGE, styled)
        self.assertIn(style.BOLD, styled)
        bare = plain(s)
        for code in (style.ORANGE, style.BOLD, style.DIM):
            self.assertNotIn(code, bare)

    def test_color_command_toggles(self):
        s = dispatch_action(new(), "/color off")
        self.assertFalse(s.color_enabled)
        self.assertTrue(state_from_dict(state_to_dict(dispatch_action(s, "/color on"))).color_enabled)

    def test_every_node_fits_40_columns_styled(self):
        s = new()._replace(message_buffer=(danger("x " * 30), gain("y " * 30)))
        for node_id in s.nodes:
            frame = render_frame(at(s, node_id, 1, 1), 40)
            self.assertEqual({visible_len(line) for line in frame.split("\n")}, {40}, node_id)

    def test_legend_has_no_ids_and_short_screens_drop_it(self):
        s = new()
        tall = plain(s)
        self.assertIn("Water Tap", tall)
        self.assertNotIn("spigot_01", tall)
        short = plain(s, height=len(tall.split("\n")) - 1)
        self.assertNotIn("Water Tap", short)

    def test_long_pack_is_capped(self):
        s = new()
        many = tuple(ALL_ITEMS_BY_ID[i] for i in ALL_ITEMS_BY_ID)
        s = s._replace(character=s.character._replace(inventory=many))
        self.assertIn("more: /pack", plain(s))

    def test_long_crew_line_is_shortened(self):
        from core.reducers import ALL_COMPANIONS_BY_ID
        s = new()._replace(current_node_id="stn_a_berth", companions=tuple(ALL_COMPANIONS_BY_ID.values()))
        self.assertIn("Crew: Radek +2", plain(s))

    def test_header_shows_hazards_when_they_do_not_fit(self):
        s = new()._replace(current_node_id="luna_pad", player_row=3, player_col=3)
        self.assertIn("No air, freezing, high radiation", plain(s))


class TestCommandsAndSaves(unittest.TestCase):
    def test_look_lists_exits_with_hazards(self):
        s = dispatch_action(new()._replace(current_node_id="stn_a_berth"), "/look")
        self.assertIn("Exit: Sub-Deck (thin air, cold)", s.message_buffer)

    def test_help_topics(self):
        self.assertIn("SURVIVAL", dispatch_action(new(), "/help survival").message_buffer[0])
        self.assertIn("HELP", dispatch_action(new(), "/help").message_buffer[0])

    def test_older_save_gets_new_names(self):
        data = state_to_dict(new())
        data["schema_version"] = 2
        data["character"]["inventory"][0]["name"] = "Copper Pipe Fitting"
        data["nodes"]["stn_a_bunkroom"]["fixtures"]["spigot_01"]["name"] = "Water Spigot"
        loaded = state_from_dict(data)
        self.assertEqual(loaded.character.inventory[0].name, "Pipe Fitting")
        self.assertEqual(loaded.nodes["stn_a_bunkroom"].fixtures["spigot_01"].name, "Water Tap")


if __name__ == "__main__":
    unittest.main()
