from flask import Flask, request, jsonify
from PIL import Image, ImageFilter, ImageEnhance
import subprocess
import uuid
import os

app = Flask(__name__)

UPLOAD_FOLDER = "temp"

os.makedirs(UPLOAD_FOLDER, exist_ok=True)


def preprocess_image(input_path):

    image = Image.open(input_path)

    image = image.convert("RGB")

    # Resize intelligently
    max_size = 1200

    image.thumbnail((max_size, max_size))

    # Slight sharpening
    image = image.filter(
        ImageFilter.SHARPEN
    )

    # Contrast boost
    enhancer = ImageEnhance.Contrast(image)

    image = enhancer.enhance(1.25)

    # Slight smoothing
    image = image.filter(
        ImageFilter.SMOOTH
    )

    image.save(input_path)


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

        preprocess_image(input_path)

        subprocess.run(
            [
                "vtracer",
                input_path,
                "-o",
                output_path,

                "--colormode",
                "color",

                "--hierarchical",

                "stacked",

                "--mode",
                "spline",

                "--filter_speckle",
                "4",

                "--color_precision",
                "6",

                "--layer_difference",
                "12",

                "--corner_threshold",
                "60",

                "--length_threshold",
                "4.0",

                "--max_iterations",
                "10",

                "--splice_threshold",
                "45"
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

    return "Professional VTracer Server Running"


if __name__ == "__main__":

    app.run(
        host="0.0.0.0",
        port=10000
    )