from flask import Flask, request, jsonify
from PIL import Image, ImageFilter, ImageEnhance
import subprocess
import uuid
import os

app = Flask(__name__)

UPLOAD_FOLDER = "temp"

os.makedirs(
    UPLOAD_FOLDER,
    exist_ok=True
)

# =====================================================
# IMAGE PREPROCESSING
# =====================================================

def preprocess_image(input_path):

    image = Image.open(input_path)

    image = image.convert("RGB")

    # Higher resolution preservation
    max_size = 1800

    image.thumbnail(
        (max_size, max_size)
    )

    # Strong sharpening
    image = image.filter(
        ImageFilter.SHARPEN
    )

    image = image.filter(
        ImageFilter.SHARPEN
    )

    # Contrast enhancement
    enhancer =
        ImageEnhance.Contrast(image)

    image =
        enhancer.enhance(1.4)

    # Edge enhancement
    image = image.filter(
        ImageFilter.EDGE_ENHANCE
    )

    image.save(input_path)

# =====================================================
# VECTORIZE ENDPOINT
# =====================================================

@app.route(
    "/vectorize",
    methods=["POST"]
)
def vectorize():

    if "image" not in request.files:

        return jsonify({
            "error":
                "No image uploaded"
        }), 400

    image =
        request.files["image"]

    uid =
        str(uuid.uuid4())

    input_path =
        f"{UPLOAD_FOLDER}/{uid}.png"

    output_path =
        f"{UPLOAD_FOLDER}/{uid}.svg"

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
                "2",

                "--color_precision",
                "8",

                "--corner_threshold",
                "75"
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

    return "Professional VTracer Server Running"

# =====================================================
# START SERVER
# =====================================================

if __name__ == "__main__":

    app.run(
        host="0.0.0.0",
        port=10000
    )