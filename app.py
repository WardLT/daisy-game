from datetime import datetime
from pathlib import Path
from typing import Optional
from functools import cache
from math import isclose
import secrets
import json


import humanize.time
from flask import Flask, request, render_template, flash, session
from werkzeug.utils import redirect
import pandas as pd
import numpy as np

app = Flask(__name__)
app.secret_key = secrets.token_urlsafe(16)

result_time = datetime(2022, 2, 20, 12, 30, 0)

answer_path = Path('answers.xlsx')
result_path = Path('results.json')


@cache
def get_answer(path: Path = answer_path) -> pd.DataFrame():
    """Load the answer spreadsheet from disk

    Adds a breed tag column which
    """
    answers = pd.read_excel(path, usecols=range(3))

    # Make breed tags
    answers['breed_tag'] = answers['breed'].apply(lambda x: x.replace(" ", "_").lower())

    # Make the fractions add to 100
    answers['fraction'] *= 100
    assert isclose(answers['fraction'].sum(), 100)

    return answers


@app.route('/', methods=['GET'])
def home():
    breeds = get_answer()['breed'].tolist()
    return render_template('home.html', breeds=breeds)


@app.route('/', methods=['POST'])
def receive():

    answers = get_answer()

    # Check if it is too late
    if datetime.now() > result_time:
        flash("It's too late now!", 'error')
        return redirect('/guesses')

    # Store the response time
    data = dict(request.form)
    data['response_time'] = datetime.now().isoformat()

    # Convert breeds to percentages
    for b in answers['breed_tag']:
        data[b] = float(data.get(b, 0))

    # Store the person's name in the session
    session['name'] = data['name']
    session['newbreed'] = data['newbreed']

    # Make sure they guess at least one breed
    score_count = sum(data.get(x, 0) for x in answers['breed_tag'])
    if score_count <= 0:
        flash('You must assign a percentage to at least one breed!', 'error')
        return redirect('/')

    with open('results.json', 'a') as fp:
        print(json.dumps(data), file=fp)

    return redirect('/guesses')


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


def get_results() -> Optional[pd.DataFrame]:
    """Get the latest guesses from contestants"""

    if not Path('results.json').exists():
        return None

    # Get the most-recent guess from each person
    results = pd.read_json('results.json', lines=True)
    results.sort_values(['response_time', 'name'], ascending=True, inplace=True)
    results.drop_duplicates('name', inplace=True)

    # Compute percentages
    total = results[breed_tags].sum(axis=1).values[:, None]
    results[breed_tags] = results[breed_tags] / total * 100
    return results


@app.route('/results')
def display_results():
    if datetime.now() < result_time:
        flash(f'You have to wait until {humanize.time.naturaltime(result_time)}!', 'error')
        return redirect('/guesses')

    # Get the results
    results = get_results()

    # Compute the KL score (contest 1)
    results['kl_score'] = 0.
    for breed, col in zip(breeds, breed_tags):
        results['kl_score'] += np.abs(results[col] - answer.get(breed, 0))

    # Compute the number of correct breeds
    results['breed_id'] = 0
    results['misses'] = 0
    for breed, col in zip(breeds, breed_tags):
        if breed in answer:
            results['breed_id'] += results[col] > 0
        else:
            results['misses'] += results[col] > 0
            results['breed_id'] -= results[col] > 0

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

    # Return the results
    breed_ideas = set(results['newbreed'])
    return render_template('results.html', results=results.to_dict('records'), breed_ideas=breed_ideas, answer=answer)
