from aura_link.protocol import Envelope, EventType, b64decode, b64encode, new_id


def test_envelope_round_trip() -> None:
    event = Envelope(
        type=EventType.TEXT_DELTA,
        session_id="session_1",
        turn_id="turn_1",
        payload={"text": "halo"},
    )
    decoded = Envelope.loads(event.dumps())
    assert decoded == event


def test_binary_round_trip() -> None:
    value = b"\x00\x01audio"
    assert b64decode(b64encode(value)) == value


def test_ids_are_prefixed_and_unique() -> None:
    first, second = new_id("turn"), new_id("turn")
    assert first.startswith("turn_")
    assert first != second

