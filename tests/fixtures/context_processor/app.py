from flask import Flask, render_template
app = Flask(__name__)
@app.context_processor
def inject_site_name():
    return {"site_name": "Fixture"}
@app.get("/")
def home():
    return render_template("home.html")
