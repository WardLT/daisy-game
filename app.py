from datetime import datetime
import secrets
import json

from flask import Flask, request, render_template, flash, session
from werkzeug.utils import redirect
import pandas as pd

app = Flask(__name__)
app.secret_key = secrets.token_urlsafe(16)

breeds = [
    "Airedale Terrier",
    "American Eskimo Dog",
    "Australian Shepherd",
    "Australian Stumpy-tail Cattle Dog",
    "Beagle",
    "Belgian Turvuren",
    "Bernese Mountain Dog",
    "Birman",
    "Bulldog",
    "Caucasian Shepherd Dog",
    "Chow",
    "Collie",
    "German Long-haired Pointer",
    "German Shepherd",
    "Havana Brown",
    "King Charles Spaniel",
    "Nova Scotia Duck Toller Retriever",
    "Rottweiler"
]

breed_tags = [x.replace(" ", "_") for x in breeds]


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
    # Get the most-recent guess from each person
    results = pd.read_json('results.json', lines=True)
    results.sort_values(['response_time', 'name'], ascending=True, inplace=True)
    results.drop_duplicates('name', inplace=True)

    # Compute percentages
    total = results[breed_tags].sum(axis=1).values[:, None]
    results[breed_tags] = results[breed_tags] / total * 100

    # Print the form
    return render_template('guesses.html', results=results.to_dict(orient='records'), breeds=breeds)
