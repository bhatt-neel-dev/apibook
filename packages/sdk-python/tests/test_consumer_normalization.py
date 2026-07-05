"""
normalize_consumer() reshapes whatever a caller passes to set_consumer/
track_consumer (string, dict, arbitrary object, or None) into the standard
3-key dict the ingest pipeline expects. Untested until now.
"""

from apilens.client.middleware import normalize_consumer, track_consumer, _read_consumer


def test_none_returns_empty_consumer():
    assert normalize_consumer(None) == {
        "consumer_id": "",
        "consumer_name": "",
        "consumer_group": "",
    }


def test_plain_string_becomes_consumer_id():
    assert normalize_consumer("  user-42  ") == {
        "consumer_id": "user-42",
        "consumer_name": "",
        "consumer_group": "",
    }


def test_dict_with_canonical_keys():
    result = normalize_consumer(
        {"consumer_id": "u1", "consumer_name": "Alice", "consumer_group": "admins"}
    )

    assert result == {"consumer_id": "u1", "consumer_name": "Alice", "consumer_group": "admins"}


def test_dict_key_aliases_id_name_group():
    result = normalize_consumer({"id": "u2", "name": "Bob", "group": "members"})

    assert result == {"consumer_id": "u2", "consumer_name": "Bob", "consumer_group": "members"}


def test_dict_id_key_takes_precedence_over_identifier_alias():
    # `id` and `identifier` are both accepted keys; `id` is checked first, so
    # it wins when both are present. This pins the actual precedence so a
    # future refactor can't silently swap it.
    result = normalize_consumer({"id": "from-id", "identifier": "from-identifier"})

    assert result["consumer_id"] == "from-id"


def test_object_with_username_attribute():
    class FakeUser:
        id = "u3"
        username = "carol"
        group = "editors"

    result = normalize_consumer(FakeUser())

    assert result == {"consumer_id": "u3", "consumer_name": "carol", "consumer_group": "editors"}


def test_object_missing_all_attributes_returns_empty_strings():
    class Empty:
        pass

    result = normalize_consumer(Empty())

    assert result == {"consumer_id": "", "consumer_name": "", "consumer_group": ""}


def test_values_are_stripped_and_coerced_to_str():
    result = normalize_consumer({"id": "  42  ", "name": None, "group": 7})

    assert result == {"consumer_id": "42", "consumer_name": "", "consumer_group": "7"}


def test_track_consumer_round_trips_through_contextvar_without_a_request():
    track_consumer(None, identifier=" alice@example.com ", name="Alice", group="admins")

    stored = _read_consumer(None)

    assert stored == {
        "consumer_id": "alice@example.com",
        "consumer_name": "Alice",
        "consumer_group": "admins",
    }


def test_track_consumer_strips_and_defaults_missing_name_and_group():
    track_consumer(None, identifier="bob@example.com")

    stored = _read_consumer(None)

    assert stored["consumer_id"] == "bob@example.com"
    assert stored["consumer_name"] == ""
    assert stored["consumer_group"] == ""
