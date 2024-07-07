from datetime import datetime, timedelta
from pathlib import Path
import json

from pytest import fixture

import shutil
import app


@fixture(autouse=True)
def test_app(tmpdir):
    # Point the answers and results to a special folder
    app._result_path = Path(tmpdir) / 'results.json'
    new_answer_path = Path(tmpdir) / 'answers.xlsx'
    shutil.copy(app._answer_path, new_answer_path)
    app._answer_path = new_answer_path

    # Make the deadline an hour from now
    app.result_time = datetime.now() + timedelta(hours=1)
    return app.app.test_client()


@fixture()
def perfect_answer():
    # Mimic a perfect answer
    answers = app.get_answer()

    perfect = {
        'name': 'Lady Perfect',
        'newbreed': 'Best'
    }
    for tag, val in zip(answers['breed_tag'], answers['fraction']):
        perfect[tag] = val
    return perfect


def test_load_answer():
    answers = app.get_answer()
    assert len(answers['breed']) > 1
    assert answers['breed_tag'].str.islower().all()
    assert not answers['breed_tag'].str.contains(' ').any()


def test_load_results(perfect_answer):
    perfect_answer['response_time'] = datetime.now().isoformat()
    with app._result_path.open('w') as fp:
        print(json.dumps(perfect_answer), file=fp)

    # Load the results from disk
    results = app.get_results()
    assert len(results) == 1


def test_submission_then_update(test_app, perfect_answer):
    """Submit an answer then change"""
    # Test loading the page
    page = test_app.get('/')
    assert page.status_code == 200

    # Submit a result
    page = test_app.post('/', data=perfect_answer, follow_redirects=False)
    assert page.status_code == 302, page.get_data(as_text=True)
    assert "too late now!" not in page.get_data(as_text=True)
    assert len(app.get_results()) == 1

    # Look at the results
    page = test_app.get('/guesses')
    assert page.status_code == 200
    assert 'Lady Perfect' in page.get_data(True)

    # Submit another answer
    perfect_answer['newbreed'] = 'A worse idea'
    page = test_app.post('/', data=perfect_answer, follow_redirects=True)
    assert page.status_code == 200
    assert 'A worse idea' in page.get_data(True)
