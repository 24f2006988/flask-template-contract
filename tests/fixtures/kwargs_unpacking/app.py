"""Static-analysis fixture; do not import or execute this app."""

from flask import Flask, render_template

app = Flask(__name__)


@app.get("/search")
def search():
    context = {"query": "all"}
    return render_template("search.html", **context)
