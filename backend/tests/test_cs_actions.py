"""Unit tests for parse_cs_action_tags in prompt.py."""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from prompt import parse_cs_action_tags


class TestParseActionTagsCleanText:
    def test_no_tags_returns_text_unchanged(self):
        text = "Initiating Circuit Stitcher. Scanning viewport."
        clean, actions = parse_cs_action_tags(text)
        assert clean == text
        assert actions == []

    def test_single_tag_stripped_from_text(self):
        text = "Stitching route.\n[ACTION: CLICK_SAVE]\nDone."
        clean, _ = parse_cs_action_tags(text)
        assert "[ACTION:" not in clean
        assert "CLICK_SAVE" not in clean

    def test_narration_before_tag_preserved(self):
        # The params capture group ([^\[]*) consumes text after the tag up to
        # the next '[', so only text *before* the tag is guaranteed to survive.
        text = "Step one.\n[ACTION: CLICK_SAVE]\nStep two."
        clean, _ = parse_cs_action_tags(text)
        assert "Step one." in clean

    def test_multiple_tags_all_stripped(self):
        text = (
            "[ACTION: DRAG_AND_DROP] Source -> SFO_Node. Destination -> Waypoint_1.\n"
            "[ACTION: DRAG_AND_DROP] Source -> Waypoint_1. Destination -> PHX_Node.\n"
            "[ACTION: CLICK_SAVE]\n"
        )
        clean, _ = parse_cs_action_tags(text)
        assert "[ACTION:" not in clean

    def test_empty_string(self):
        clean, actions = parse_cs_action_tags("")
        assert clean == ""
        assert actions == []

    def test_only_tag_leaves_empty_clean(self):
        text = "[ACTION: CLICK_SAVE]"
        clean, _ = parse_cs_action_tags(text)
        assert clean == ""

    def test_whitespace_only_after_strip_is_empty(self):
        text = "  [ACTION: CLICK_SAVE]  "
        clean, _ = parse_cs_action_tags(text)
        assert clean.strip() == ""


class TestParseActionTagsCommands:
    def test_click_save_command(self):
        _, actions = parse_cs_action_tags("[ACTION: CLICK_SAVE]")
        assert len(actions) == 1
        assert actions[0]["command"] == "CLICK_SAVE"

    def test_drag_and_drop_command(self):
        _, actions = parse_cs_action_tags(
            "[ACTION: DRAG_AND_DROP] Source -> SFO_Node. Destination -> PHX_Node."
        )
        assert actions[0]["command"] == "DRAG_AND_DROP"

    def test_drag_source_extracted(self):
        _, actions = parse_cs_action_tags(
            "[ACTION: DRAG_AND_DROP] Source -> SFO_Node. Destination -> Waypoint_1."
        )
        assert actions[0]["source"] == "SFO_Node"

    def test_drag_destination_extracted(self):
        _, actions = parse_cs_action_tags(
            "[ACTION: DRAG_AND_DROP] Source -> SFO_Node. Destination -> Waypoint_1."
        )
        assert actions[0]["destination"] == "Waypoint_1"

    def test_target_param_extracted(self):
        _, actions = parse_cs_action_tags("[ACTION: CLICK] Target -> SaveBtn.")
        assert actions[0]["target"] == "SaveBtn"

    def test_no_params_still_returns_action(self):
        _, actions = parse_cs_action_tags("[ACTION: CLICK_SAVE]")
        assert actions[0] == {"command": "CLICK_SAVE"}

    def test_multiple_actions_count(self):
        text = (
            "[ACTION: DRAG_AND_DROP] Source -> A. Destination -> B.\n"
            "[ACTION: DRAG_AND_DROP] Source -> B. Destination -> C.\n"
            "[ACTION: CLICK_SAVE]\n"
        )
        _, actions = parse_cs_action_tags(text)
        assert len(actions) == 3

    def test_multiple_actions_ordered(self):
        text = (
            "[ACTION: DRAG_AND_DROP] Source -> A. Destination -> B.\n"
            "[ACTION: CLICK_SAVE]\n"
        )
        _, actions = parse_cs_action_tags(text)
        assert actions[0]["command"] == "DRAG_AND_DROP"
        assert actions[1]["command"] == "CLICK_SAVE"

    def test_command_leading_whitespace_stripped(self):
        # \s* after ACTION: handles leading spaces before the command word
        _, actions = parse_cs_action_tags("[ACTION:  DRAG_AND_DROP] Source -> X. Destination -> Y.")
        assert actions[0]["command"] == "DRAG_AND_DROP"

    def test_unknown_command_passthrough(self):
        _, actions = parse_cs_action_tags("[ACTION: TELEPORT] Source -> X.")
        assert actions[0]["command"] == "TELEPORT"

    def test_multiline_params(self):
        text = "[ACTION: DRAG_AND_DROP] Source -> NodeA.\nDestination -> NodeB."
        _, actions = parse_cs_action_tags(text)
        assert actions[0].get("source") == "NodeA"
        assert actions[0].get("destination") == "NodeB"


class TestParseActionTagsReturnType:
    def test_returns_tuple(self):
        result = parse_cs_action_tags("hello")
        assert isinstance(result, tuple)
        assert len(result) == 2

    def test_clean_text_is_str(self):
        clean, _ = parse_cs_action_tags("hello [ACTION: CLICK_SAVE] world")
        assert isinstance(clean, str)

    def test_actions_is_list(self):
        _, actions = parse_cs_action_tags("hello")
        assert isinstance(actions, list)

    def test_each_action_is_dict(self):
        _, actions = parse_cs_action_tags("[ACTION: CLICK_SAVE]")
        for a in actions:
            assert isinstance(a, dict)

    def test_each_action_has_command_key(self):
        _, actions = parse_cs_action_tags(
            "[ACTION: DRAG_AND_DROP] Source -> A. Destination -> B.\n[ACTION: CLICK_SAVE]"
        )
        for a in actions:
            assert "command" in a
