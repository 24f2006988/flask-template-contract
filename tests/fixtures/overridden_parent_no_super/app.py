from flask import Flask, render_template

app = Flask(__name__)


@app.get("/")
def home():
    return render_template("child.html", child_value="Child", parent_value="Unused")
