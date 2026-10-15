from flask import Flask, render_template

first = Flask("first")
second = Flask("second")


@first.get("/first")
def first_page():
    return render_template("first.html", title="First")


@second.get("/second")
def second_page():
    return render_template("second.html")
