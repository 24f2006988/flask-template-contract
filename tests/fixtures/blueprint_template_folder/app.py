from flask import Flask, Blueprint, render_template
app = Flask(__name__)
admin = Blueprint("admin", __name__, template_folder="templates")
@admin.get("/dashboard")
def dashboard():
    return render_template("admin.html", heading="Admin")
app.register_blueprint(admin)
