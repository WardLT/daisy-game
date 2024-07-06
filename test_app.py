from datetime import datetime
from pathlib import Path
import json

from app import get_answer, get_results


def test_load_answer():
    answers = get_answer()
    assert len(answers['breed']) > 1
    assert answers['breed_tag'].str.islower().all()
    assert not answers['breed_tag'].str.contains(' ').any()


def test_load_results(tmpdir):
    # Mimic a perfect answer
    results_path = Path(tmpdir) / 'results.json'
    answers = get_answer()

    perfect = {
        'name': 'Lady Perfect',
        'new_breed': 'Best',
        'response_time': datetime.now().isoformat()
    }
    for tag, val in zip(answers['breed_tag'], answers['fraction']):
        perfect[tag] = val
    with results_path.open('w') as fp:
        print(json.dumps(perfect), file=fp)

    # Load the results from disk
    results = get_results(result_path=results_path)
