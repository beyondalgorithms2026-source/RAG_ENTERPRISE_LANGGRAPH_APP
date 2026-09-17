from scripts.run_rt06_live import QUESTIONS


def test_rt06_and_rt16_have_distinct_real_stack_questions():
    assert set(QUESTIONS) == {"rt06", "rt16"}
    assert QUESTIONS["rt06"] != QUESTIONS["rt16"]
