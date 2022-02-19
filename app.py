from datetime import datetime
import json

from flask import Flask, request, render_template
from werkzeug.utils import redirect

app = Flask(__name__)

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


@app.route('/', methods=['GET'])
def home():
    return render_template('home.html', breeds=breeds)


@app.route('/', methods=['POST'])
def receive():
    # Store the response time
    data = dict(request.form)
    data['response_time'] = datetime.now().isoformat()

    with open('results.json', 'a') as fp:
        print(json.dumps(data), file=fp)

    return redirect('/')
