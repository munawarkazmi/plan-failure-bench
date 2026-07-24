"""Tests for the world model schema, loader, and renderer.

The checker is not built yet; these tests pin down the layer it will stand
on: strict loading, consistency validation, state construction, goal
evaluation, and invariant semantics.
"""

import copy
import json
from pathlib import Path

import pytest

from plan_failure_bench.loader import load_environment
from plan_failure_bench.render import render_environment
from plan_failure_bench.schema import (
    Goal,
    Holding,
    ItemIn,
    NeverEnter,
    NeverHoldIn,
    RobotAt,
    SchemaError,
    State,
)

REPO_ROOT = Path(__file__).resolve().parent.parent
HOUSE_01 = REPO_ROOT / "environments" / "house_01.json"
OFFICE_01 = REPO_ROOT / "environments" / "office_01.json"

MINIMAL = {
    "name": "minimal",
    "rooms": ["a", "b"],
    "doors": [{"name": "d_ab", "connects": ["a", "b"], "state": "closed"}],
    "items": [
        {"name": "ball", "category": "ball", "properties": ["soft"], "room": "b", "portable": True, "description": "a ball"}
    ],
    "robot": {"room": "a", "capabilities": ["goto", "open", "pick", "place"]},
    "invariants": [
        {"kind": "never_hold_in", "property": "soft", "room": "a", "text": "Never carry soft items into room a."}
    ],
}


def write_env(tmp_path, data):
    p = tmp_path / "env.json"
    p.write_text(json.dumps(data), encoding="utf-8")
    return p


def load_mutated(tmp_path, mutate):
    data = copy.deepcopy(MINIMAL)
    mutate(data)
    return load_environment(write_env(tmp_path, data))


class TestLoadHouse01:
    def test_loads(self):
        env = load_environment(HOUSE_01)
        assert env.name == "house_01"
        assert len(env.rooms) == 7
        assert len(env.doors) == 6
        assert len(env.items) == 10
        assert len(env.invariants) == 2

    def test_capabilities_exclude_unlock(self):
        env = load_environment(HOUSE_01)
        assert "unlock" not in env.capabilities

    def test_cellar_has_no_doors(self):
        env = load_environment(HOUSE_01)
        assert env.adjacency("cellar") == ()

    def test_locked_store_room(self):
        env = load_environment(HOUSE_01)
        assert env.door("d_living_store").state == "locked"

    def test_tv_is_fixed(self):
        env = load_environment(HOUSE_01)
        assert env.item("tv").portable is False


class TestLoadOffice01:
    """Pins the structural facts the office_01 seed suite is designed around.

    The annex disconnection test matters most: unlike the cellar, archive and
    strong_room each have a door, so the renderer never prints a "has no
    doors" line for them and unreachability must be inferred from the
    connection list.
    """

    def test_loads(self):
        env = load_environment(OFFICE_01)
        assert env.name == "office_01"
        assert len(env.rooms) == 9
        assert len(env.doors) == 8
        assert len(env.items) == 11
        assert len(env.invariants) == 2

    def test_capabilities_exclude_unlock(self):
        env = load_environment(OFFICE_01)
        assert "unlock" not in env.capabilities

    def test_ring_route_choice(self):
        # The five ring rooms form a cycle, so every ring-to-ring trip has
        # two routes. house_01 also contains one cycle (kitchen, hallway,
        # living_room) but only through a closed door; here the ring is
        # open except at d_workshop_studio.
        env = load_environment(OFFICE_01)
        ring = ["lobby", "canteen", "server_room", "workshop", "studio"]
        for a, b in zip(ring, ring[1:] + ring[:1]):
            assert any(b == other for _, other in env.adjacency(a)), (a, b)

    def test_annex_connects_only_to_itself(self):
        env = load_environment(OFFICE_01)
        assert env.adjacency("archive") == (("d_archive_strong", "strong_room"),)
        assert env.adjacency("strong_room") == (("d_archive_strong", "archive"),)

    def test_locked_supply_room(self):
        env = load_environment(OFFICE_01)
        assert env.door("d_workshop_supply").state == "locked"

    def test_photocopier_is_fixed(self):
        env = load_environment(OFFICE_01)
        assert env.item("photocopier").portable is False

    def test_invariant_kinds(self):
        env = load_environment(OFFICE_01)
        kinds = {type(inv) for inv in env.invariants}
        assert kinds == {NeverEnter, NeverHoldIn}

    def test_greasy_property_carried_by_several_items(self):
        # house_01's never_hold_in properties each belonged to exactly one
        # item; here the model must track which items carry the property.
        env = load_environment(OFFICE_01)
        greasy = [i.name for i in env.items if "greasy" in i.properties]
        assert sorted(greasy) == ["oil_can", "spanner_large", "spanner_small"]

    def test_render_never_says_annex_has_no_doors(self):
        env = load_environment(OFFICE_01)
        text = render_environment(env)
        assert "has no doors" not in text
        assert "(locked)" in text
        assert "Fixed in place." in text


class TestValidation:
    def test_minimal_is_valid(self, tmp_path):
        env = load_mutated(tmp_path, lambda d: None)
        assert env.validate() == []

    @pytest.mark.parametrize(
        "mutate, fragment",
        [
            (lambda d: d["doors"][0].update(connects=["a", "z"]), "unknown room 'z'"),
            (lambda d: d["doors"][0].update(connects=["a", "a"]), "to itself"),
            (lambda d: d["doors"][0].update(state="ajar"), "unknown state 'ajar'"),
            (lambda d: d["items"][0].update(room="z"), "unknown room 'z'"),
            (lambda d: d["items"][0].update(name="a"), "used more than once"),
            (lambda d: d["doors"][0].update(name="ball"), "used more than once"),
            (lambda d: d["robot"].update(room="z"), "unknown room 'z'"),
            (lambda d: d["robot"].update(capabilities=["goto", "fly"]), "'fly' is not in the global action vocabulary"),
            (lambda d: d["robot"].update(capabilities=["pick", "place"]), "must include 'goto'"),
            (lambda d: d["invariants"][0].update(room="z"), "unknown room 'z'"),
            (lambda d: d["invariants"][0].update(property="wet"), "carried by no item"),
        ],
    )
    def test_inconsistency_rejected(self, tmp_path, mutate, fragment):
        with pytest.raises(SchemaError, match="inconsistent"):
            load_mutated(tmp_path, mutate)
        try:
            load_mutated(tmp_path, mutate)
        except SchemaError as exc:
            assert fragment in str(exc)

    @pytest.mark.parametrize(
        "mutate",
        [
            lambda d: d.update(extra=1),
            lambda d: d.pop("invariants"),
            lambda d: d["doors"][0].pop("state"),
            lambda d: d["doors"][0].update(connects=["a"]),
            lambda d: d["items"][0].update(portable="yes"),
            lambda d: d["items"][0].update(surprise=1),
            lambda d: d["invariants"][0].update(kind="never_sing"),
            lambda d: d["invariants"][0].update(text=""),
            lambda d: d["robot"].pop("capabilities"),
        ],
    )
    def test_malformed_json_shape_rejected(self, tmp_path, mutate):
        with pytest.raises(SchemaError):
            load_mutated(tmp_path, mutate)

    def test_all_problems_reported_at_once(self, tmp_path):
        def mutate(d):
            d["robot"]["room"] = "z"
            d["items"][0]["room"] = "y"

        try:
            load_mutated(tmp_path, mutate)
        except SchemaError as exc:
            assert "'z'" in str(exc) and "'y'" in str(exc)


class TestState:
    def test_initial(self):
        env = load_environment(HOUSE_01)
        state = State.initial(env)
        assert state.robot_room == "hallway"
        assert state.holding is None
        assert state.item_room("torch") == "cellar"
        assert state.door_state("d_hall_bedroom") == "closed"

    def test_hashable_and_equal(self):
        env = load_environment(HOUSE_01)
        assert State.initial(env) == State.initial(env)
        assert len({State.initial(env), State.initial(env)}) == 1

    def test_held_item_has_no_room(self):
        env = load_environment(HOUSE_01)
        s = State.initial(env)
        held = State(
            robot_room="kitchen",
            holding="cup_red",
            door_states=s.door_states,
            item_rooms=tuple(p for p in s.item_rooms if p[0] != "cup_red"),
        )
        assert held.item_room("cup_red") is None

    def test_unknown_names_raise(self):
        env = load_environment(HOUSE_01)
        s = State.initial(env)
        with pytest.raises(KeyError):
            s.item_room("ghost")
        with pytest.raises(KeyError):
            s.door_state("d_ghost")


class TestGoal:
    def test_satisfied_on_initial(self):
        env = load_environment(HOUSE_01)
        s = State.initial(env)
        assert Goal((RobotAt("hallway"),)).satisfied(s)
        assert not Goal((ItemIn("cup_red", "bedroom"),)).satisfied(s)
        assert not Goal((Holding("cup_red"),)).satisfied(s)

    def test_satisfied_count_for_partial(self):
        env = load_environment(HOUSE_01)
        s = State.initial(env)
        goal = Goal((RobotAt("hallway"), ItemIn("cup_red", "bedroom")))
        assert goal.satisfied_count(s) == 1
        assert not goal.satisfied(s)

    def test_held_item_satisfies_no_room_goal(self):
        env = load_environment(HOUSE_01)
        s = State.initial(env)
        held = State("kitchen", "cup_red", s.door_states, tuple(p for p in s.item_rooms if p[0] != "cup_red"))
        assert not ItemIn("cup_red", "kitchen").satisfied(held)
        assert Holding("cup_red").satisfied(held)


class TestInvariants:
    def test_never_enter(self):
        env = load_environment(HOUSE_01)
        s = State.initial(env)
        inv = NeverEnter(room="nursery", text="Stay out of the nursery.")
        assert inv.holds(s, env)
        inside = State("nursery", None, s.door_states, s.item_rooms)
        assert not inv.holds(inside, env)

    def test_never_hold_in(self):
        env = load_environment(HOUSE_01)
        s = State.initial(env)
        inv = env.invariants[0]
        assert isinstance(inv, NeverHoldIn)

        empty_handed_in_nursery = State("nursery", None, s.door_states, s.item_rooms)
        assert inv.holds(empty_handed_in_nursery, env)

        rooms_without_knife = tuple(p for p in s.item_rooms if p[0] != "knife")
        knife_in_nursery = State("nursery", "knife", s.door_states, rooms_without_knife)
        assert not inv.holds(knife_in_nursery, env)

        knife_in_kitchen = State("kitchen", "knife", s.door_states, rooms_without_knife)
        assert inv.holds(knife_in_kitchen, env)

        rooms_without_teddy = tuple(p for p in s.item_rooms if p[0] != "teddy")
        teddy_in_nursery = State("nursery", "teddy", s.door_states, rooms_without_teddy)
        assert inv.holds(teddy_in_nursery, env)


class TestRender:
    def test_deterministic(self):
        env = load_environment(HOUSE_01)
        assert render_environment(env) == render_environment(env)

    def test_invariant_texts_verbatim(self):
        env = load_environment(HOUSE_01)
        text = render_environment(env)
        for inv in env.invariants:
            assert inv.text in text

    def test_discloses_unreachability_evidence(self):
        env = load_environment(HOUSE_01)
        text = render_environment(env)
        assert "cellar has no doors" in text
        assert "(locked)" in text
        assert "Fixed in place." in text

    def test_discloses_capabilities_and_gripper(self):
        env = load_environment(HOUSE_01)
        text = render_environment(env)
        assert "close, goto, open, pick, place" in text
        assert "unlock" not in text
        assert "at most one item" in text
