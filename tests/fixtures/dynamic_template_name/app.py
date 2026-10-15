"""Static-analysis fixture; do not import or execute this app."""

from flask import Flask, render_template

app = Flask(__name__)


@app.get("/page")
def page():
    template_name = "page.html"
    return render_template(template_name, heading="A page")
