from flask import Flask, request, jsonify
import subprocess
import uuid
import os

app = Flask(__name__)

UPLOAD_FOLDER = "temp"

os.makedirs(UPLOAD_FOLDER, exist_ok=True)

@app.route("/vectorize", methods=["POST"])
def vectorize():

    if "image" not in request.files:
        return jsonify({
            "error": "No image uploaded"
        }), 400

    image = request.files["image"]

    uid = str(uuid.uuid4())

    input_path = f"{UPLOAD_FOLDER}/{uid}.png"
    output_path = f"{UPLOAD_FOLDER}/{uid}.svg"

    image.save(input_path)

    try:

        subprocess.run(
            [
                "vtracer",
                input_path,
                "-o",
                output_path
            ],
            check=True
        )

        with open(output_path, "r") as file:
            svg = file.read()

        os.remove(input_path)
        os.remove(output_path)

        return jsonify({
            "svg": svg
        })

    except Exception as e:

        return jsonify({
            "error": str(e)
        }), 500


@app.route("/")
def home():

    return "VTracer Server Running"


if __name__ == "__main__":
    app.run(
        host="0.0.0.0",
        port=10000
    )