from flask import Flask, Blueprint, render_template
app = Flask(__name__)
first = Blueprint("first", __name__, template_folder="first_templates")
second = Blueprint("second", __name__, template_folder="second_templates")
@app.get("/")
def home():
    return render_template("same.html")
app.register_blueprint(first)
app.register_blueprint(second)
