from flask import Flask, render_template
app = Flask(__name__)
@app.template_global()
def edition():
    return "community"
@app.get("/")
def home():
    return render_template("home.html")
