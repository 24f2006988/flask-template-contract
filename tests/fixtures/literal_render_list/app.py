from flask import Flask, render_template
app = Flask(__name__)
@app.get("/")
def home():
    return render_template(["preferred.html", "fallback.html"], title="List")
