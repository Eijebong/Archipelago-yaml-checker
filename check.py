from WebHostLib.check import roll_options
from flask import Flask, request

app = Flask(__name__)

@app.route("/check_yaml", methods=["POST"])
def hello_world():
    yaml_content = request.files["data"]
    results, _ = roll_options({"file.yaml": yaml_content})

    file_result = results["file.yaml"]
    if file_result is True:
        return {}

    return {"error": file_result}

app.run(host="0.0.0.0")
