"""The intro of a new game (models/intro.py): the harbour's scene at once, then
the walk to Uncle Gared's door, whose scenes end it; and what a save keeps of it."""

import os
from types import SimpleNamespace

import pytest

from src.config.constants import PICTURES_PATH, TILE_SIZE
from src.models import intro as intro_mod
from src.models.intro import ARRIVAL, DONE, FIND_SHOP, SCENES, SHOP_POINT, Intro, find_shop_spot
from src.ui.helper_modules.dialogue import answer_dialogue

SPOT = (1000.0, 2000.0)
FAR = (SPOT[0] + 10 * TILE_SIZE, SPOT[1])


def test_constants_the_tests_rely_on():
    assert intro_mod.ARRIVAL_REACH_TILES == 1.5
    assert intro_mod.SHOP_DOOR_SEARCH_TILES == 2.0


def test_a_new_game_opens_on_the_harbour_scene_once():
    intro = Intro(shop_spot=SPOT)
    assert intro.scene_due(FAR) == "harbour"
    assert intro.scene_due(FAR) is None          # it is playing
    assert not intro.finding_shop                # no rings or note under the dialogue


def test_following_the_address_sends_the_player_to_find_the_shop():
    intro = Intro(shop_spot=SPOT)
    intro.scene_due(FAR)
    assert intro.answered() is None
    assert intro.stage == FIND_SHOP
    assert intro.finding_shop
    assert intro.scene_due(FAR) is None          # nothing until they get there


def test_reaching_the_door_plays_the_shop_scenes_and_ends_the_intro():
    intro = Intro(FIND_SHOP, shop_spot=SPOT)
    near = (SPOT[0] + 1.4 * TILE_SIZE, SPOT[1])
    assert intro.scene_due((SPOT[0] + 1.6 * TILE_SIZE, SPOT[1])) is None
    assert intro.scene_due(near) == "shop"
    assert intro.answered() == "uncle"
    assert intro.answered() == "hug"
    assert intro.stage == FIND_SHOP              # still on until the last answer
    assert intro.answered() is None
    assert intro.stage == DONE
    assert not intro.finding_shop
    assert intro.scene_due(SPOT) is None


def test_save_keeps_the_stage_and_not_the_scene_on_screen():
    intro = Intro(shop_spot=SPOT)
    intro.scene_due(FAR)
    saved = intro.to_save()
    assert saved == {"stage": ARRIVAL}
    again = Intro(DONE, shop_spot=SPOT)
    again.load(saved)
    assert again.scene_due(FAR) == "harbour"     # the scene shown when saved opens again


@pytest.mark.parametrize("data", [None, {}, {"stage": "nonsense"}, "arrival"])
def test_a_save_without_the_intro_has_had_it(data):
    intro = Intro(shop_spot=SPOT)
    intro.load(data)
    assert intro.stage == DONE
    assert intro.scene_due(SPOT) is None


def _door(x, y, step):
    return SimpleNamespace(threshold=(x, y), step=step)


def test_the_shop_spot_is_the_step_of_the_door_nearest_the_shop():
    px, py = SHOP_POINT
    doors = [
        _door(px + 3 * TILE_SIZE, py, (0.0, 0.0)),            # too far
        _door(px + 30, py, (1.0, 1.0)),
        _door(px - 5, py + 10, (2.0, 2.0)),                   # the nearest
        _door(px, py, None),                                  # no step: not usable
    ]
    assert find_shop_spot(doors) == (2.0, 2.0)


def test_without_a_door_there_the_player_arrives_at_the_point_itself():
    assert find_shop_spot([]) == SHOP_POINT


def test_every_scene_has_its_picture_and_voice_and_its_chain_ends():
    sounds = os.path.join("assets", "sound")
    for name, scene in SCENES.items():
        assert os.path.exists(os.path.join(PICTURES_PATH, f"{scene.picture}.png")), name
        assert any(f.startswith(scene.sound + ".") for f in os.listdir(sounds)), name
        assert scene.next is None or scene.next in SCENES
    for start in intro_mod.OPENING_SCENE.values():
        seen, name = set(), start
        while name is not None:
            assert name not in seen
            seen.add(name)
            name = SCENES[name].next


def test_an_answer_goes_to_the_dialogues_callback_or_closes_it():
    answers = []
    dialogue = SimpleNamespace(on_answer=answers.append)
    state = SimpleNamespace(dialogue=dialogue, time_level=1, previous_time_level=3)
    answer_dialogue(state, "Follow the Address")
    assert answers == ["Follow the Address"]
    assert state.dialogue is dialogue and state.time_level == 1   # the callback decides

    state.dialogue = SimpleNamespace(on_answer=None)
    answer_dialogue(state, "Bye")
    assert state.dialogue is None and state.time_level == 3
