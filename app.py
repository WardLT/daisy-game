from datetime import datetime
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

breeds = [
    "Airedale Terrier",
    "American Eskimo Dog",
    "American Foxhound",
    "American Pit Bull Terrier",
    "Australian Shepherd",
    "Australian Stumpy-tail Cattle Dog",
    "Beagle",
    "Belgian Turvuren",
    "Bernese Mountain Dog",
    "Bulldog",
    "Caucasian Shepherd Dog",
    "Chow",
    "Collie",
    "German Long-haired Pointer",
    "German Shepherd",
    "Golden Retriever",
    "Havana Brown",
    "King Charles Spaniel",
    "Nova Scotia Duck Toller Retriever",
    "Rottweiler"
]

breed_tags = [x.replace(" ", "_") for x in breeds]

answer = {
    "Beagle": 35.9,
    "American Pit Bull Terrier": 20.5,
    "Chow": 14.4,
    "American Foxhound": 14.1,
    "Golden Retriever": 8,
    "German Shepherd": 7.1
}

assert isclose(sum(answer.values()), 100)
assert all(k in breeds for k in answer)

result_time = datetime(2022, 2, 20, 20, 0, 0)


@app.route('/', methods=['GET'])
def home():
    return render_template('home.html', breeds=breeds)


@app.route('/', methods=['POST'])
def receive():
    # Store the response time
    data = dict(request.form)
    data['response_time'] = datetime.now().isoformat()

    # Convert breeds to percentages
    for b in breed_tags:
        data[b] = float(data.get(b, 0))

    # Store the person's name in the session
    session['name'] = data['name']
    session['newbreed'] = data['newbreed']

    # Make sure they guess at least one breed
    score_count = sum(data.get(x, 0) for x in breed_tags)
    if score_count <= 0:
        flash('You must assign a percentage to at least one breed!', 'error')
        return redirect('/')

    with open('results.json', 'a') as fp:
        print(json.dumps(data), file=fp)

    return redirect('/guesses')


@app.route('/guesses')
def guesses():
    results = get_results()

    # Get the unique breed ideas
    breed_ideas = set(results['newbreed'])

    # Print the form
    return render_template('guesses.html', results=results.to_dict(orient='records'), breeds=breeds,
                           breed_ideas=breed_ideas)


def get_results() -> pd.DataFrame:
    """Get the latest guesses from contestants"""
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
    for breed, col in zip(breeds, breed_tags):
        if breed in answer:
            results['breed_id'] += results[col] > 0
        else:
            results['breed_id'] -= results[col] > 0

    # Mark the champions!
    results['grand_champ'] = results['kl_score'] == results['kl_score'].min()
    results['coward_champ'] = results['breed_id'] == results['breed_id'].max()
    results['both'] = results[['grand_champ', 'coward_champ']].all(axis=1)

    # Store the results
    results['award'] = ''
    results.loc[results['grand_champ'], 'award'] = 'Grand Champion! 💪'
    results.loc[results['coward_champ'], 'award'] = 'Coward Champ 👑'
    results.loc[results['both'], 'award'] = 'Ultimate Champ!! 👑💪🐶'

    # Sort values so that the KL champ is on top
    results.sort_values('kl_score', ascending=True, inplace=True)

    # Return the results
    breed_ideas = set(results['newbreed'])
    return render_template('results.html', results=results.to_dict('records'), breed_ideas=breed_ideas)
