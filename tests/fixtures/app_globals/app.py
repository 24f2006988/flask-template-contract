from flask import Flask, render_template
app = Flask(__name__)
app.jinja_env.globals.update(product_name="Fixture")
@app.get("/")
def home():
    return render_template("home.html")
