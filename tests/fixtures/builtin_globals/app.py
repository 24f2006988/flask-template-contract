"""Static-analysis fixture; do not import or execute this app."""

from flask import Flask, render_template

app = Flask(__name__)


@app.get("/context")
def context():
    return render_template("context.html", title="Built-ins")
