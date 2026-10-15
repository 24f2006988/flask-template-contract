from flask import Flask, render_template
app = Flask(__name__)
def render_page(name, **context):
    return render_template(name, **context)
@app.get("/")
def home():
    return render_page("home.html", title="Wrapped")
