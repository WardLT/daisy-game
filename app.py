import os
from datetime import datetime
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Optional
from functools import cache
from math import isclose
import secrets
import shutil
import json

import humanize.time
from flask import Flask, request, render_template, flash, session, send_file, url_for
from flask_basicauth import BasicAuth
from werkzeug.utils import redirect
import pandas as pd
import numpy as np

# Make the flask app, including a password for the admin page
app = Flask(__name__)
app.secret_key = secrets.token_urlsafe(16)

app.config['BASIC_AUTH_USERNAME'] = 'admin'
app.config['BASIC_AUTH_PASSWORD'] = os.environ.get('DOLLYGAME_PASSWD', 'admin')
basic_auth = BasicAuth(app)

# Randomize the name of the answer download and upload page
download_page = secrets.token_urlsafe(16) + '.xlsx'

result_time = datetime(2022, 2, 20, 12, 30, 0)

_answer_path = Path('answers.xlsx')
_result_path = Path('results.json')


@cache
def get_answer(path: Optional[Path] = None) -> pd.DataFrame():
    """Load the answer spreadsheet from disk

    Adds a breed tag column which
    """
    path = path or _answer_path
    answers = pd.read_excel(path, usecols=range(3))

    # Make breed tags
    answers['breed_tag'] = answers['breed'].apply(lambda x: x.replace(" ", "_").lower())

    # Make the fractions add to 100
    answers['fraction'] *= 100
    if not isclose(answers['fraction'].sum(), 100):
        raise ValueError(f'The fraction of breeds does not batch up to the correct format')

    return answers


def get_results(result_path: Optional[Path] = None,
                answer_path: Optional[Path] = None) -> Optional[pd.DataFrame]:
    """Get the latest guesses from contestants"""
    result_path = result_path or _result_path
    if not Path(result_path).exists():
        return None

    # Get the breed tags
    answer_data = get_answer(answer_path)
    answer = dict(zip(answer_data['breed_tag'], answer_data['fraction']))
    breed_tags = answer_data['breed_tag'].values

    # Get the most-recent guess from each person
    results = pd.read_json(result_path, lines=True)
    results.sort_values(['response_time', 'name'], ascending=False, inplace=True)
    results.drop_duplicates('name', keep='first', inplace=True)

    # Compute percentages
    total = results[breed_tags].sum(axis=1).values[:, None]
    results[breed_tags] = results[breed_tags] / total * 100

    # Compute the KL score (contest 1)
    results['kl_score'] = 0.
    for breed, amount in answer.items():
        results['kl_score'] += np.abs(results[breed] - amount)

    # Compute the number of correct breeds
    results['breed_id'] = 0
    results['misses'] = 0
    for breed, amount in answer.items():
        if amount > 0:
            results['breed_id'] += results[breed] > 0
        else:
            results['misses'] += results[breed] > 0
            results['breed_id'] -= results[breed] > 0

    # Mark the champions!
    results['grand_champ'] = np.isclose(results['kl_score'], results['kl_score'].min())
    results['coward_champ'] = np.isclose(results['breed_id'], results['breed_id'].max())
    results['cat_lover'] = np.isclose(results['misses'], results['misses'].max())
    results['both'] = results[['grand_champ', 'coward_champ']].all(axis=1)

    # Store the results
    results['award'] = ''
    results.loc[results['grand_champ'], 'award'] += 'Grand Champion! 💪'
    results.loc[results['coward_champ'], 'award'] += 'Coward Champ 👑'
    results.loc[results['cat_lover'], 'award'] += 'Most misses 😼'
    results.loc[results['both'], 'award'] = 'Ultimate Champ!! 👑💪🐶'

    # Sort values so that the KL champ is on top
    results.sort_values('kl_score', ascending=True, inplace=True)

    return results


@app.route('/', methods=['GET'])
def home():
    breeds = get_answer()['breed'].tolist()
    return render_template('home.html', breeds=breeds, done=datetime.now() > result_time)


@app.route('/', methods=['POST'])
def receive():
    answers = get_answer()

    # Check if it is too late
    if datetime.now() > result_time:
        flash("It's too late now!", 'error')
        return redirect(url_for('guesses'))

    # Store the response time
    data = dict(request.form)
    data['response_time'] = datetime.now().isoformat()

    # Convert breeds to percentages
    data['name'] = data['name'].strip()
    for b in answers['breed_tag']:
        val = data.get(b, '0').strip()
        if len(val) < 1:
            val = 0
        data[b] = float(val)

    # Store the person's name in the session
    session['name'] = data['name']
    session['newbreed'] = data['newbreed']

    # Make sure they guess at least one breed
    score_count = sum(data.get(x, 0) for x in answers['breed_tag'])
    if score_count <= 0:
        flash('You must assign a percentage to at least one breed!', 'error')
        return redirect(url_for('home'))

    with open(_result_path, 'a') as fp:
        print(json.dumps(data), file=fp)

    return redirect(url_for('guesses'))


@app.route('/guesses')
def guesses():
    # Get the results and answers
    results = get_results()
    answer = get_answer()

    # Get the unique breed ideas
    breed_ideas = set(results['newbreed']) if results is not None else set()

    # Print the form
    return render_template('guesses.html',
                           results=None if results is None else results.to_dict(orient='records'),
                           breeds=answer['breed'].tolist(),
                           breed_ideas=breed_ideas,
                           answer=answer,
                           done=datetime.now() > result_time)


@app.route('/results')
def user_results():
    if datetime.now() < result_time:
        flash(f'You have to wait until {humanize.time.naturaltime(result_time)}!', 'error')
        return redirect(url_for('guesses'))

    return display_results()


def display_results():
    """Render the results page"""

    # Get the results
    results = get_results()

    # Get the answers as dictionary
    actual_breeds = get_answer().query('fraction > 0')
    answer = dict(zip(actual_breeds['breed'], actual_breeds['fraction']))

    # Return the results
    breed_ideas = set(results['newbreed'])
    return render_template('results.html',
                           results=results.to_dict('records'),
                           breed_ideas=breed_ideas,
                           answer=answer)


@app.get('/admin')
@basic_auth.required
def admin():
    """Display the admin page"""
    return render_template('admin.html', download_page=download_page)


@app.get(f'/{download_page}')
@basic_auth.required
def download_answers():
    return send_file(_answer_path, as_attachment=True, download_name=_answer_path.name)


@app.post('/admin')
def upload_answers():
    """Receive the uploaded answers"""

    # Make sure a file was provided
    if 'file' not in request.files:
        flash('You did not provide a file', category='error')
        return redirect(url_for('admin'))
    file = request.files['file']
    if file.filename == '':
        flash('You did not provide a file', category='error')
        return redirect(url_for('admin'))

    # Download and make sure it is formatted correctly
    with TemporaryDirectory() as tmp:
        tmp_path = Path(tmp) / 'answers.xlsx'
        file.save(tmp_path)

        try:
            get_answer(tmp_path)
        except ValueError as err:
            flash(str(err), category='error')
            return redirect(url_for('admin'))

        # If it does read correctly, replace the existing answers
        shutil.move(tmp_path, _answer_path)
        flash('Answer list uploaded correctly')

        # Clear the cache for the answer loader
        get_answer.cache_clear()
        return redirect(url_for('home'))
