from flask import Flask, render_template, request
app = Flask(__name__)
@app.get("/")
def home():
    name = request.args.get("template")
    return render_template(name)
