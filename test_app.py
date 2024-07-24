from datetime import datetime, timedelta
from pathlib import Path
from io import BytesIO
import base64
import json

from pytest import fixture

import shutil
import app
from app import load_votes

creds = base64.b64encode(b"dolly:dolly").decode("utf-8")
headers = {'Authorization': f'Basic {creds}'}


@fixture(autouse=True)
def test_app(tmpdir):
    # Point the answers and results to a special folder
    app._result_path = Path(tmpdir) / 'results.json'
    app._votes_path = Path(tmpdir) / 'votes.csv'
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
    """Submit an answer then change it"""
    # Test loading the page
    page = test_app.get('/', headers=headers)
    assert page.status_code == 200

    # Submit a result
    page = test_app.post('/', data=perfect_answer, follow_redirects=False, headers=headers)
    assert page.status_code == 302, page.get_data(as_text=True)
    assert "too late now!" not in page.get_data(as_text=True)
    assert len(app.get_results()) == 1

    # Look at the results
    page = test_app.get('/guesses', headers=headers)
    assert page.status_code == 200
    assert 'Lady Perfect' in page.get_data(True)

    # Submit another answer
    perfect_answer['newbreed'] = 'A worse idea'
    page = test_app.post('/', data=perfect_answer, follow_redirects=True, headers=headers)
    assert page.status_code == 200
    assert 'A worse idea' in page.get_data(True)


def test_too_late(test_app, perfect_answer):
    app.result_time = datetime.now() - timedelta(minutes=1)

    page = test_app.post('/', data=perfect_answer, follow_redirects=True, headers=headers)
    assert 'too late' in page.get_data(True)

    # Make sure the result isn't on the webpage
    page = test_app.get('/guesses', headers=headers)
    assert page.status_code == 200
    assert 'Lady Perfect' not in page.get_data(True)


def test_results(test_app, perfect_answer):
    page = test_app.post('/', data=perfect_answer, follow_redirects=True, headers=headers)
    assert page.status_code == 200
    assert 'Lady Perfect' in page.get_data(True)

    # Make sure the results are not yet visible
    page = test_app.get('/results', follow_redirects=True, headers=headers)
    assert page.status_code == 200
    assert 'The Answers' not in page.get_data(True)
    assert 'You have to wait' in page.get_data(True)

    # Increment the time and see if the results button shows up
    app.result_time = datetime.now() - timedelta(minutes=1)
    page = test_app.get('/results', headers=headers)
    assert page.status_code == 200
    assert 'Ultimate Champ!' in page.get_data(True)
    assert 'Pick me!' in page.get_data(True)

    # Cast a vote for a nonexistant candidate
    page = test_app.post('/vote', headers=headers, data={'name': perfect_answer['name'], 'choice': 'Not in'},
                         follow_redirects=True)
    assert page.status_code == 200
    assert 'not in the voting table' in page.get_data(True)
    assert load_votes() == {}

    # Cast a vote for a real candidate
    page = test_app.post('/vote', headers=headers,
                         data={'name': perfect_answer['name'], 'choice': perfect_answer['newbreed']},
                         follow_redirects=True)
    assert page.status_code == 200
    assert load_votes() == {perfect_answer['name']: perfect_answer['newbreed']}

    # Try to cast after the vote time
    app.result_time -= app.voting_duration
    page = test_app.post('/vote', headers=headers,
                         data={'name': perfect_answer['name'], 'choice': perfect_answer['newbreed']},
                         follow_redirects=True)
    assert page.status_code == 200
    assert '<b>Your choice</b>' in page.get_data(True)
    assert 'The voting period has ended' in page.get_data(True)
    assert '👑  (1)' in page.get_data(True)


def test_admin(test_app, perfect_answer):
    page = test_app.get('/admin')
    assert page.status_code == 401

    creds = base64.b64encode(b"admin:admin").decode("utf-8")
    headers = {'Authorization': f'Basic {creds}'}
    page = test_app.get('/admin', headers=headers)
    assert page.status_code == 200

    page = test_app.get('/admin/results', headers=headers)
    assert page.status_code == 200

    last_mod = app._answer_path.lstat().st_mtime
    io = BytesIO(app._answer_path.read_bytes())
    page = test_app.post('/admin', content_type='multipart/form-data', headers=headers,
                         data={'file': (io, 'example.xlsx')}, follow_redirects=True)
    assert page.status_code == 200
    assert app._answer_path.lstat().st_mtime > last_mod
