from flask import Flask, render_template
from flask_babel import Babel

app = Flask(__name__)
Babel(app)


@app.get("/")
def home():
    return render_template("home.html")
