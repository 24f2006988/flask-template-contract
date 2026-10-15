"""Static-analysis fixture; do not import or execute this app."""

from flask import Flask, render_template

app = Flask(__name__)


@app.get("/dashboard")
def dashboard():
    return render_template("child.html", heading="Dashboard")
