from app import get_answer


def test_load_answer():
    answers = get_answer()
    assert len(answers['breed']) > 1
    assert answers['breed_tag'].str.islower().all()
    assert not answers['breed_tag'].str.contains(' ').any()

