from flask import Flask, request, jsonify
from PIL import Image, ImageFilter, ImageEnhance
import subprocess
import uuid
import os

app = Flask(__name__)

UPLOAD_FOLDER = "temp"

os.makedirs(UPLOAD_FOLDER, exist_ok=True)

# =====================================================
# IMAGE PREPROCESSING
# =====================================================

def preprocess_image(input_path):

    image = Image.open(input_path)

    image = image.convert("RGB")

    # Preserve more detail
    max_size = 2200

    image.thumbnail((max_size, max_size))

    # Strong sharpness enhancement
    sharpness = ImageEnhance.Sharpness(image)

    image = sharpness.enhance(2.8)

    # Strong contrast enhancement
    contrast = ImageEnhance.Contrast(image)

    image = contrast.enhance(1.6)

    # Edge enhancement
    image = image.filter(ImageFilter.EDGE_ENHANCE_MORE)

    image.save(input_path)

# =====================================================
# VECTORIZE ENDPOINT
# =====================================================

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

                "--input",
                input_path,

                "--output",
                output_path,

                "--colormode",
                "color",

                "--mode",
                "spline",

                "--filter_speckle",
                "1",

                "--color_precision",
                "10",

                "--corner_threshold",
                "95"
            ],
            check=True
        )

        with open(
            output_path,
            "r",
            encoding="utf-8"
        ) as file:

            svg = file.read()

        if os.path.exists(input_path):
            os.remove(input_path)

        if os.path.exists(output_path):
            os.remove(output_path)

        return jsonify({
            "svg": svg
        })

    except Exception as e:

        if os.path.exists(input_path):
            os.remove(input_path)

        if os.path.exists(output_path):
            os.remove(output_path)

        return jsonify({
            "error": str(e)
        }), 500

# =====================================================
# HOME ROUTE
# =====================================================

@app.route("/")
def home():

    return "Professional HD VTracer Server Running"

# =====================================================
# START SERVER
# =====================================================

if __name__ == "__main__":

    app.run(
        host="0.0.0.0",
        port=10000
    )