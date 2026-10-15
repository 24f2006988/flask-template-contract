"""Static-analysis fixture; do not import or execute this app."""

from flask import Flask, render_template

app = Flask(__name__)


@app.get("/profile")
def profile():
    return render_template("profile.html", title="Profile")
