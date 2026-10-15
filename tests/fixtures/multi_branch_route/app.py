from flask import Flask, render_template, request
app = Flask(__name__)
@app.get("/")
def home():
    if request.args.get("full"):
        title = "Full"
    return render_template("home.html", title=title)
