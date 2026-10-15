from flask import Flask, render_template
app = Flask(__name__)
@app.get("/")
def home():
    return render_template("child.html", title="Child", base_title="Base")
