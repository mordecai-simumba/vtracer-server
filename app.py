from flask import Flask, request, jsonify
from PIL import Image, ImageFilter, ImageEnhance, ImageOps
import base64
import io
import os
import subprocess
import uuid

app = Flask(__name__)

UPLOAD_FOLDER = "temp"
os.makedirs(UPLOAD_FOLDER, exist_ok=True)

# Keep uploads reasonable for Render memory limits.
app.config["MAX_CONTENT_LENGTH"] = 18 * 1024 * 1024

DEFAULT_MAX_SIDE = 2600
DEFAULT_FIRESTORE_SAFE_SVG_BYTES = 850_000

# =====================================================
# SMALL HELPERS
# =====================================================

def clamp_int(value, default, min_value, max_value):
    try:
        parsed = int(value)
    except Exception:
        parsed = default

    return max(min_value, min(max_value, parsed))


def bool_param(name, default=False):
    value = request.form.get(name, request.args.get(name, ""))

    if value == "":
        return default

    return value.strip().lower() in {"1", "true", "yes", "y", "on"}


def safe_remove(path):
    try:
        if path and os.path.exists(path):
            os.remove(path)
    except Exception:
        pass


# =====================================================
# IMAGE LOADING + STANDARDIZATION
# =====================================================

def load_image(input_path):
    image = Image.open(input_path)
    image = ImageOps.exif_transpose(image)

    if image.mode in ("RGBA", "LA", "P"):
        rgba = image.convert("RGBA")
        white = Image.new("RGBA", rgba.size, (255, 255, 255, 255))
        white.alpha_composite(rgba)
        return white.convert("RGB")

    return image.convert("RGB")


def resize_for_quality(image, max_side):
    width, height = image.size
    largest = max(width, height)

    if largest > max_side:
        scale = max_side / float(largest)
        new_size = (
            max(1, int(width * scale)),
            max(1, int(height * scale))
        )
        return image.resize(new_size, Image.Resampling.LANCZOS)

    # Small screenshots/text scans trace better when gently enlarged.
    if largest < 1200:
        scale = min(2.0, 1200 / float(largest))
        new_size = (
            max(1, int(width * scale)),
            max(1, int(height * scale))
        )
        return image.resize(new_size, Image.Resampling.LANCZOS)

    return image


def otsu_threshold(gray_image):
    histogram = gray_image.histogram()
    total = sum(histogram)

    if total <= 0:
        return 180

    sum_total = sum(index * count for index, count in enumerate(histogram))
    sum_background = 0
    weight_background = 0
    max_variance = 0
    threshold = 180

    for index, count in enumerate(histogram):
        weight_background += count

        if weight_background == 0:
            continue

        weight_foreground = total - weight_background

        if weight_foreground == 0:
            break

        sum_background += index * count
        mean_background = sum_background / weight_background
        mean_foreground = (sum_total - sum_background) / weight_foreground

        variance = weight_background * weight_foreground * (mean_background - mean_foreground) ** 2

        if variance > max_variance:
            max_variance = variance
            threshold = index

    return threshold


def edge_density(gray_image):
    sample = gray_image.resize((220, 220), Image.Resampling.BILINEAR)
    edges = sample.filter(ImageFilter.FIND_EDGES)
    histogram = edges.histogram()
    bright_pixels = sum(histogram[90:])
    total_pixels = sample.size[0] * sample.size[1]
    return bright_pixels / float(total_pixels)


def looks_text_or_line_art(image):
    gray = ImageOps.grayscale(image)
    density = edge_density(gray)
    colors = image.resize((160, 160), Image.Resampling.BILINEAR).getcolors(maxcolors=256 * 256)
    unique_colors = len(colors or [])

    # Text scans and diagrams tend to have many edges and fewer meaningful color regions.
    return density > 0.12 or unique_colors < 96


def standardize_for_exam(image, style="exam_bw"):
    image = ImageOps.autocontrast(image, cutoff=1)
    image = ImageEnhance.Contrast(image).enhance(1.22)
    image = ImageEnhance.Sharpness(image).enhance(1.65)
    image = image.filter(ImageFilter.UnsharpMask(radius=1.1, percent=155, threshold=3))

    style = (style or "exam_bw").lower()

    if style in {"color", "original", "photo_color"}:
        return image.convert("RGB")

    gray = ImageOps.grayscale(image)
    gray = ImageOps.autocontrast(gray, cutoff=1)
    gray = ImageEnhance.Contrast(gray).enhance(1.35)
    gray = gray.filter(ImageFilter.UnsharpMask(radius=1.0, percent=170, threshold=2))

    if style in {"soft_gray", "grayscale", "grey", "gray"}:
        return gray.convert("RGB")

    if looks_text_or_line_art(image):
        threshold = otsu_threshold(gray)
        # Slightly bias towards white paper and strong black writing.
        threshold = max(145, min(210, threshold + 8))
        bw = gray.point(lambda pixel: 255 if pixel > threshold else 0, mode="1")
        return bw.convert("RGB")

    # For photos/scenes, keep grayscale tones instead of destroying detail.
    return gray.convert("RGB")


def preprocess_image(input_path, output_path, max_side, style):
    image = load_image(input_path)
    image = resize_for_quality(image, max_side=max_side)
    image = standardize_for_exam(image, style=style)
    image.save(output_path, format="PNG", optimize=True)
    return image.size


# =====================================================
# HD SVG WRAPPER
# =====================================================

def encode_png_bytes(image):
    buffer = io.BytesIO()
    image.save(buffer, format="PNG", optimize=True)
    return buffer.getvalue()


def shrink_image(image, factor=0.90):
    width, height = image.size
    new_size = (
        max(320, int(width * factor)),
        max(320, int(height * factor))
    )

    if new_size == image.size:
        return image

    return image.resize(new_size, Image.Resampling.LANCZOS)


def build_hd_embedded_svg(input_path, max_svg_bytes):
    image = Image.open(input_path).convert("RGB")

    for _ in range(12):
        png_bytes = encode_png_bytes(image)
        encoded = base64.b64encode(png_bytes).decode("ascii")
        width, height = image.size

        svg = f'''<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" viewBox="0 0 {width} {height}">
  <rect width="100%" height="100%" fill="#ffffff"/>
  <image href="data:image/png;base64,{encoded}" x="0" y="0" width="{width}" height="{height}" preserveAspectRatio="xMidYMid meet"/>
</svg>'''

        if len(svg.encode("utf-8")) <= max_svg_bytes or max(image.size) <= 900:
            return svg, width, height, len(svg.encode("utf-8"))

        image = shrink_image(image)

    width, height = image.size
    return svg, width, height, len(svg.encode("utf-8"))


# =====================================================
# VTRACER
# =====================================================

def run_vtracer(input_path, output_path, style):
    style = (style or "exam_bw").lower()
    colormode = "color" if style in {"color", "original", "photo_color"} else "bw"

    detailed_command = [
        "vtracer",
        "--input", input_path,
        "--output", output_path,
        "--colormode", colormode,
        "--hierarchical", "stacked",
        "--mode", "spline",
        "--filter_speckle", "1",
        "--color_precision", "8",
        "--gradient_step", "8",
        "--corner_threshold", "35",
        "--length_threshold", "2.0",
        "--max_iterations", "20",
        "--splice_threshold", "30",
        "--path_precision", "4"
    ]

    fallback_command = [
        "vtracer",
        "--input", input_path,
        "--output", output_path,
        "--colormode", "color" if colormode == "color" else "bw",
        "--mode", "spline"
    ]

    result = subprocess.run(
        detailed_command,
        capture_output=True,
        text=True,
        timeout=150
    )

    if result.returncode == 0:
        return result

    # Some VTracer builds have a smaller CLI surface. Keep the service alive.
    fallback_result = subprocess.run(
        fallback_command,
        capture_output=True,
        text=True,
        timeout=150
    )

    if fallback_result.returncode == 0:
        return fallback_result

    return result


def read_svg(path):
    with open(path, "r", encoding="utf-8") as file:
        return file.read()


def polish_svg(svg):
    # Make traced SVG print in clean exam style without relying on CSS outside the SVG.
    if "<svg" in svg and "shape-rendering" not in svg[:500]:
        svg = svg.replace(
            "<svg",
            "<svg shape-rendering=\"geometricPrecision\" text-rendering=\"geometricPrecision\"",
            1
        )

    return svg.strip()


# =====================================================
# VECTORIZE ENDPOINT
# =====================================================

@app.route("/vectorize", methods=["POST"])
def vectorize():
    if "image" not in request.files:
        return jsonify({"error": "No image uploaded"}), 400

    image = request.files["image"]
    uid = str(uuid.uuid4())

    original_path = os.path.join(UPLOAD_FOLDER, f"{uid}_original")
    clean_path = os.path.join(UPLOAD_FOLDER, f"{uid}_clean.png")
    trace_path = os.path.join(UPLOAD_FOLDER, f"{uid}.svg")

    mode = request.form.get("mode", request.args.get("mode", "hybrid")).strip().lower()
    style = request.form.get("style", request.args.get("style", "exam_bw")).strip().lower()
    max_side = clamp_int(
        request.form.get("maxSide", request.args.get("maxSide", DEFAULT_MAX_SIDE)),
        DEFAULT_MAX_SIDE,
        900,
        4200
    )
    max_svg_bytes = clamp_int(
        request.form.get("maxSvgBytes", request.args.get("maxSvgBytes", DEFAULT_FIRESTORE_SAFE_SVG_BYTES)),
        DEFAULT_FIRESTORE_SAFE_SVG_BYTES,
        250_000,
        4_000_000
    )
    include_trace = bool_param("includeTrace", default=False)

    image.save(original_path)

    try:
        width, height = preprocess_image(
            input_path=original_path,
            output_path=clean_path,
            max_side=max_side,
            style=style
        )

        trace_svg = ""
        trace_error = ""

        if mode in {"trace", "auto", "hybrid"} or include_trace:
            result = run_vtracer(clean_path, trace_path, style=style)

            if result.returncode == 0 and os.path.exists(trace_path):
                trace_svg = polish_svg(read_svg(trace_path))
            else:
                trace_error = result.stderr or result.stdout or "VTracer failed"

        if mode == "trace":
            if not trace_svg:
                return jsonify({"error": trace_error or "VTracer failed"}), 500

            response = {
                "svg": trace_svg,
                "renderMode": "trace",
                "style": style,
                "width": width,
                "height": height,
                "svgBytes": len(trace_svg.encode("utf-8"))
            }
            return jsonify(response)

        hd_svg, hd_width, hd_height, hd_bytes = build_hd_embedded_svg(
            input_path=clean_path,
            max_svg_bytes=max_svg_bytes
        )

        selected_mode = "hd_embedded_svg"
        selected_svg = hd_svg

        if mode == "auto" and trace_svg:
            trace_bytes = len(trace_svg.encode("utf-8"))
            # Use traced SVG only when it is not huge and likely to be readable enough.
            if trace_bytes <= max_svg_bytes and trace_bytes < hd_bytes * 1.35:
                selected_mode = "trace"
                selected_svg = trace_svg

        response = {
            "svg": selected_svg,
            "renderMode": selected_mode,
            "style": style,
            "width": hd_width if selected_mode == "hd_embedded_svg" else width,
            "height": hd_height if selected_mode == "hd_embedded_svg" else height,
            "svgBytes": len(selected_svg.encode("utf-8")),
            "note": "Text-heavy images are clearer in hd_embedded_svg mode because letters remain real pixels inside an SVG wrapper. Use mode=trace when you need editable vector paths."
        }

        if include_trace and trace_svg:
            response["traceSvg"] = trace_svg
            response["traceSvgBytes"] = len(trace_svg.encode("utf-8"))

        if trace_error:
            response["traceWarning"] = trace_error[:1000]

        return jsonify(response)

    except subprocess.TimeoutExpired:
        return jsonify({"error": "Vectorization timed out. Try a smaller image."}), 500

    except Exception as e:
        return jsonify({"error": str(e)}), 500

    finally:
        safe_remove(original_path)
        safe_remove(clean_path)
        safe_remove(trace_path)


# =====================================================
# HEALTH ROUTES
# =====================================================

@app.route("/")
def home():
    return "Professional HD VTracer Server Running"


@app.route("/health")
def health():
    return jsonify({"status": "ok"})


# =====================================================
# START SERVER
# =====================================================

if __name__ == "__main__":
    app.run(
        host="0.0.0.0",
        port=10000
    )
