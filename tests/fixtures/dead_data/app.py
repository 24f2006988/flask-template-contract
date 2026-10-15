"""Static-analysis fixture; do not import or execute this app."""

from flask import Flask, render_template

app = Flask(__name__)


@app.get("/")
def index():
    return render_template("index.html", title="Welcome", unused_message="Not shown")
