from flask import Flask, render_template
app = Flask(__name__)
@app.get("/")
def home():
    return render_template("home.html", title="Locals", items=[1, 2])
