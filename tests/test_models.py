import json
from pathlib import Path

from teach_me.models import (
    Bank,
    Err,
    Ok,
    Question,
    parse_bank,
    parse_question,
)

SAMPLE_BANK = Path(__file__).resolve().parent.parent / "examples" / "sample-bank.json"


def _q(**overrides):
    base = {
        "id": 1,
        "question": "What is 2 + 2?",
        "options": ["3", "4", "5"],
        "correct": [1],
        "topics": ["Math"],
    }
    return {**base, **overrides}


def test_question_derived_fields():
    q = Question(
        id=1,
        question="Pick the vowels",
        options=("a", "b", "e"),
        correct=(0, 2),
        topics=("Letters",),
    )
    assert q.answer_letters == ("A", "C")
    assert q.is_multi is True


def test_parse_question_ok_and_defaults_topics():
    result = parse_question(_q(topics=None))
    assert isinstance(result, Ok)
    assert result.value.topics == ("General",)
    assert result.value.answer_letters == ("B",)


def test_parse_question_maps_optional_bank_fields():
    result = parse_question(_q(source="td", set="Set 1", category="Compute"))
    assert isinstance(result, Ok)
    assert (result.value.source, result.value.set_name, result.value.category) == (
        "td",
        "Set 1",
        "Compute",
    )


def test_parse_question_sorts_correct_indices():
    result = parse_question(_q(options=["a", "b", "c"], correct=[2, 0]))
    assert isinstance(result, Ok)
    assert result.value.correct == (0, 2)


def test_parse_question_rejects_out_of_range_index():
    result = parse_question(_q(correct=[9]))
    assert isinstance(result, Err)
    assert "outside" in result.message


def test_parse_question_rejects_bad_shapes():
    for bad in [
        "not a dict",
        _q(id="x"),
        _q(question="  "),
        _q(options=["only one"]),
        _q(correct=[]),
        _q(correct=[True]),
        _q(explanation=5),
    ]:
        assert isinstance(parse_question(bad), Err)


def test_parse_bank_rejects_duplicate_ids():
    result = parse_bank([_q(id=1), _q(id=1)])
    assert isinstance(result, Err)
    assert "duplicate" in result.message


def test_parse_bank_reports_all_problems():
    result = parse_bank([_q(id=1), _q(id=2, correct=[99])])
    assert isinstance(result, Err)


def test_parse_bank_rejects_empty_and_non_list():
    assert isinstance(parse_bank([]), Err)
    assert isinstance(parse_bank({"questions": []}), Err)


def test_sample_bank_is_valid():
    result = parse_bank(json.loads(SAMPLE_BANK.read_text()))
    assert isinstance(result, Ok), result
    bank = result.value
    assert isinstance(bank, Bank)
    assert len(bank) == 10
    assert "Astronomy" in bank.topics()
    assert any(q.is_multi for q in bank.questions)
