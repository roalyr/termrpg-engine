"""Work skills, daily jobs, fatigue, sleep and overnight restocking."""
import unittest

from core import routine
from core.actions import dispatch_action
from core.presets import init_game_state, DEFAULT_DATA_DIR
from core.reducers import ALL_ITEMS_BY_ID
from core.types import Exposure, FixtureState
from tests.helpers import on, menu_line
from ui.render import render_frame


def new(anchor=1, routine_choice=1):
    return init_game_state(DEFAULT_DATA_DIR, "Tester", anchor, routine_choice)


def awake(state, turns):
    return state._replace(woke_at=state.cycle - turns)


def ids(state):
    return [i.id for i in state.character.inventory]


class TestSkills(unittest.TestCase):
    def test_routine_gives_a_head_start(self):
        self.assertEqual(new(1, 1).skills["engineering"], 30)
        self.assertEqual(new(1, 2).skills["survival"], 30)
        self.assertIn("cold_bypass", new(1, 2).character.unlocked_capabilities)
        self.assertEqual(new(1, 3).skills["logistics"], 30)

    def test_actions_pay_the_matching_skill(self):
        s = dispatch_action(new(), "/search personal_locker")
        self.assertEqual(s.skills["logistics"], routine.XP_SEARCH)
        s = on(new()._replace(character=new().character._replace(inventory=(ALL_ITEMS_BY_ID["tool_prybar"],))),
               "freight_crate")
        s = dispatch_action(s, "f")
        self.assertEqual(s.skills["engineering"], 30 + routine.XP_PRY)

    def test_character_panel_shows_level_and_next_perk(self):
        lines = dispatch_action(new(), "c").message_buffer
        self.assertIn("ENGINEERING 2 (30/90 XP). Opening, repairing, bypassing and smelting.", lines)
        self.assertIn("  Next at 3: Forge pry-bars from ore at the smelter.", lines)


class TestJobs(unittest.TestCase):
    def test_rotation_is_deterministic(self):
        day1 = [j.id for j in routine.jobs_for_day(new().job_catalog, 1)]
        day2 = [j.id for j in routine.jobs_for_day(new().job_catalog, 2)]
        self.assertEqual(day1, ["job_scrap_bin", "job_algae_vat", "job_sub_patrol"])
        self.assertEqual(len(set(day1) & set(day2)), 0)
        self.assertEqual(day1, [j.id for j in routine.jobs_for_day(new().job_catalog, 1)])

    def test_use_job_completes_and_pays(self):
        s = dispatch_action(on(new(), "salvage_bin"), "f")
        job = next(j for j in s.jobs if j.id == "job_scrap_bin")
        self.assertTrue(job.done)
        self.assertIn("scrip_shift", ids(s))
        self.assertTrue(any(m.startswith("+ Job done: Empty the Berth 04 scrap bin") for m in s.message_buffer))

    def test_stay_job_counts_turns(self):
        s = new()._replace(current_node_id="stn_a_sub")
        for _ in range(6):
            s = dispatch_action(s, "/wait")
        self.assertTrue(next(j for j in s.jobs if j.id == "job_sub_patrol").done)
        self.assertIn("seal_patch", ids(s))

    def test_deliver_job_takes_items_on_arrival(self):
        s = new()
        s = s._replace(jobs=routine.jobs_for_day(s.job_catalog, 2),  # includes the smelter delivery
                       character=s.character._replace(inventory=(ALL_ITEMS_BY_ID["scrap_metal"],) * 3))
        s = dispatch_action(on(s, "hatch_smelter"), "g")
        self.assertEqual(s.current_node_id, "luna_smelter")
        self.assertEqual(ids(s).count("scrap_metal"), 1)
        self.assertIn("chit_transit", ids(s))

    def test_jobs_panel(self):
        lines = dispatch_action(new(), "j").message_buffer
        self.assertEqual(lines[0], "JOBS, DAY 1 (morning shift):")
        self.assertTrue(any("[ ] Walk a 6-turn patrol in the Sub-Deck (0/6)" in m for m in lines))


class TestFatigueAndSleep(unittest.TestCase):
    def test_tired_warning_once_and_slower_work(self):
        s = awake(new(), routine.TIRED_AFTER - 1)
        s1 = dispatch_action(s, "/wait")
        self.assertTrue(any("You're tired" in m for m in s1.message_buffer))
        s2 = dispatch_action(s1, "/wait")
        self.assertFalse(any("You're tired" in m for m in s2.message_buffer))
        searched = dispatch_action(on(s2, "personal_locker"), "f")
        self.assertEqual(searched.cycle, s2.cycle + 2)

    def test_collapse_in_safe_room_sleeps_in_place(self):
        s = awake(new()._replace(current_node_id="stn_a_hab"), routine.COLLAPSE_AFTER - 1)
        s1 = dispatch_action(s, "/wait")
        self.assertEqual((s1.day, s1.current_node_id), (2, "stn_a_hab"))
        self.assertIn("You fall asleep where you stand.", s1.message_buffer)

    def test_collapse_somewhere_hostile_means_medics(self):
        base = new()
        s = base._replace(current_node_id="stn_a_sub", character=base.character._replace(
            inventory=(ALL_ITEMS_BY_ID["ration_dry"],)))
        s1 = dispatch_action(awake(s, routine.COLLAPSE_AFTER - 1), "/wait")
        self.assertEqual((s1.day, s1.current_node_id), (2, "stn_a_bunkroom"))
        self.assertNotIn("ration_dry", ids(s1))

    def test_sleep_needs_a_bunk_and_some_tiredness(self):
        self.assertIn("not tired enough", dispatch_action(new(), "/sleep").message_buffer[0])
        away = awake(new()._replace(current_node_id="stn_a_hab"), 40)
        self.assertIn("no bunk here", dispatch_action(away, "/sleep").message_buffer[0])

    def test_sleep_starts_a_new_day(self):
        s = awake(on(new(), "crew_bunk"), 40)
        s = s._replace(character=s.character._replace(exposure=Exposure(3.0, 1.0, 2.0)))
        self.assertIn("U sleep", menu_line(s))
        slept = dispatch_action(s, "u")
        self.assertEqual(slept.day, 2)
        self.assertEqual(slept.woke_at, slept.cycle)
        self.assertEqual(slept.cycle, s.cycle + routine.NIGHT_TURNS)
        self.assertEqual(slept.character.exposure, Exposure(0.0, 0.0, 0.0))
        self.assertEqual(slept.jobs, routine.jobs_for_day(s.job_catalog, 2))

    def test_restock_overnight_but_not_unique_finds(self):
        s = dispatch_action(on(new(), "salvage_bin"), "f")
        s = dispatch_action(on(s, "personal_locker"), "f")
        berth, bunk = s.nodes["stn_a_berth"], s.nodes["stn_a_bunkroom"]
        self.assertEqual(berth.fixtures["salvage_bin"].state, FixtureState.SPENT.value)
        self.assertIn("Restocks overnight.", menu_line(on(s, "salvage_bin")))
        slept = routine.start_day(s, "stn_a_bunkroom")
        self.assertEqual(slept.nodes["stn_a_berth"].fixtures["salvage_bin"].state, FixtureState.ACTIVE.value)
        self.assertEqual(slept.nodes["stn_a_bunkroom"].fixtures["personal_locker"].state, FixtureState.SPENT.value)

    def test_harvest_regrows_overnight(self):
        s = dispatch_action(on(new(1, 2), "algae_basin"), "u")
        self.assertEqual(s.nodes["stn_a_hab"].fixtures["algae_basin"].state, FixtureState.SPENT.value)
        slept = routine.start_day(s, "stn_a_bunkroom")
        self.assertEqual(slept.nodes["stn_a_hab"].fixtures["algae_basin"].state, FixtureState.ACTIVE.value)

    def test_side_panel_shows_day_and_awake(self):
        frame = render_frame(awake(new(), 64)._replace(color_enabled=False), 40)
        self.assertIn("Day 1 · Night", frame)
        self.assertIn("Awake 64/90", frame)
        self.assertIn("J jobs", frame)


if __name__ == "__main__":
    unittest.main()
