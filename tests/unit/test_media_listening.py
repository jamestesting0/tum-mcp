from tum_mcp.course.media.listening import align, judge, tokens


def words(text: str, start: float, step: float = 0.4) -> list[dict]:
    return [
        {"word": word, "start": start + i * step, "end": start + i * step + 0.3}
        for i, word in enumerate(text.split())
    ]


def test_tokens_say_numbers_and_names_the_way_a_narrator_does() -> None:
    assert tokens("score is 1 .5, then 0.75 and −1") == [
        *["score", "is", "one", "point", "five", "then"],
        *["zero", "point", "seven", "five", "and", "minus", "one"],
    ]
    assert tokens("NoOp checks") == tokens("no op check's")
    assert tokens("In 1956 and 2024") == tokens("In nineteen fifty-six and twenty twenty-four")


def test_a_swallowed_word_is_unclear_while_a_matching_sentence_is_not() -> None:
    expected = [
        {
            "key": "b01/1",
            "text": "Two rooms, A and B, may each begin dirty.",
            "start": 0.0,
            "end": 3.2,
        },
        {"key": "b01/2", "text": "The score is one point five.", "start": 4.0, "end": 6.4},
    ]
    heard = words("Two rooms and B. Mage begin dirty.", 0.0) + words("The score is 1.5.", 4.0)
    aligned = align(expected, heard)
    verdict = judge(aligned, heard)
    assert aligned[1]["match"] == 1.0
    assert any(flag.startswith("unclear b01/1") for flag in verdict["flags"])
    assert not any("b01/2" in flag for flag in verdict["flags"])


def test_a_dropped_negation_and_an_unplanned_silence_are_flagged() -> None:
    expected = [
        {
            "key": "c1/1",
            "text": "Arc consistency does not assign values.",
            "start": 0.0,
            "end": 3.0,
        },
        {"key": "c1/2", "text": "It removes unsupported values.", "start": 3.4, "end": 9.0},
    ]
    heard = words("Arc consistency does assign values.", 0.0) + words("It removes", 3.4)
    heard += words("unsupported values.", 7.0)
    flags = judge(align(expected, heard), heard)["flags"]
    assert any(flag == "missing c1/1: not" for flag in flags)
    assert any(flag.startswith("silence") for flag in flags)


def test_a_dropped_clause_in_a_long_sentence_is_flagged() -> None:
    said = "Without a dynamics model the agent {}estimates action values from many simulated runs "
    said += "and keeps the best one for each state."
    expected = [{"key": "e/7", "text": said.format("can still "), "start": 0.0, "end": 9.0}]
    heard = words(said.format("").replace("the agent ", ""), 0.0)
    aligned = align(expected, heard)
    assert aligned[0]["match"] >= 0.8
    assert judge(aligned, heard)["flags"] == ["dropped e/7: 4 words in a row not heard"]
