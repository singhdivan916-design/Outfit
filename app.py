from flask import Flask, request, send_file, jsonify
import requests
from PIL import Image
from io import BytesIO
import os

# ================= FALLBACK CONFIG =================

fallback_ids = [
    "211000000",
    "214000000",
    "208000000",
    "203000000",
    "204000000",
    "205000000",
    "212000000"
]

DEFAULT_ID = "710034057"

app = Flask(__name__)
session = requests.Session()

# ================= CONFIG =================

BACKGROUND_FILENAME = "outfit.png"

ICON_SIZE = (95, 95)

# PERFECT CHARACTER SIZE
CHARACTER_RENDER_SIZE = (750, 750)

# ================= POSITIONS (FIXED FOR 8 HEXAGONS) =================
# Perfectly mapped to a symmetrical zigzag grid: Left column (Mask, Emote, Pet, Weapon) 
# and Right column (Shirt, Pants, Armor, Shoes)
HEX_POSITIONS = {
    "mask":   (190, 100),  # Top-Left
    "emote":  (40, 240),   # Mid-Left 1
    "pet":    (190, 390),  # Mid-Left 2
    "weapon": (40, 580),   # Bottom-Left

    "shirt":  (830, 100),  # Top-Right
    "pants":  (980, 240),  # Mid-Right 1
    "armor":  (830, 390),  # Mid-Right 2
    "shoes":  (980, 580)   # Bottom-Right
}

# ================= FETCH ICON =================

def fetch_icon(icon_id, size=ICON_SIZE, is_character=False):
    try:
        # ================= CHARACTER =================
        if is_character:
            url = (
                "https://raw.githubusercontent.com/"
                "danggerr88-alt/danger-character-api/main/pngs/"
                f"{icon_id}.png"
            )
            r = session.get(url, timeout=10)
            if r.status_code == 200:
                img = Image.open(BytesIO(r.content)).convert("RGBA")
                # REMOVE TRANSPARENT EMPTY SPACE
                bbox = img.getbbox()
                if bbox:
                    img = img.crop(bbox)
                # KEEP PERFECT RATIO
                w, h = img.size
                ratio = min(size[0] / w, size[1] / h)
                new_size = (int(w * ratio), int(h * ratio))
                img = img.resize(new_size, Image.Resampling.LANCZOS)
                return img

        # ================= NORMAL ICONS =================
        ids_to_try = []
        if icon_id and str(icon_id) != "0":
            ids_to_try.append(str(icon_id))
        for fid in fallback_ids:
            if fid not in ids_to_try:
                ids_to_try.append(fid)

        for i in ids_to_try:
            try:
                url = f"https://iconapi.wasmer.app/{i}"
                r = session.get(url, timeout=10)
                if r.status_code == 200:
                    img = Image.open(BytesIO(r.content)).convert("RGBA")
                    return img.resize(size, Image.Resampling.LANCZOS)
            except:
                continue
    except:
        pass
    return None

# ================= ROUTES =================

@app.route('/', methods=['GET', 'POST'])
def home():
    return jsonify({
        "name": "Outfit Image Generator API",
        "version": "4.0",
        "endpoints": {
            "/outfit-image": {
                "method": "GET, POST",
                "params": ["uid", "key"]
            },
            "/health": {
                "method": "GET"
            }
        }
    })

@app.route('/health', methods=['GET', 'POST'])
def health_check():
    return jsonify({"status": "healthy"})

# ================= MAIN API =================

@app.route('/outfit-image', methods=['GET', 'POST'])
def outfit_image():
    # ================= SUPPORT GET & POST =================
    if request.method == 'POST':
        body = request.get_json(silent=True) or {}
        uid = body.get('uid') or request.args.get('uid')
        key = body.get('key') or request.args.get('key')
    else:
        uid = request.args.get('uid')
        key = request.args.get('key')

    # ================= VALIDATION =================
    if not uid:
        return jsonify({"error": "UID parameter required"}), 400

    # ================= FETCH PLAYER DATA =================
    try:
        api_url = f"https://info.killersharmabot.online/player-info?uid={uid}"
        response = session.get(api_url, timeout=10)
        response.raise_for_status()
        data = response.json()
    except requests.exceptions.RequestException as e:
        return jsonify({"error": f"API Down: {str(e)}"}), 500
    except ValueError:
        return jsonify({"error": "Invalid JSON response"}), 500

    # ================= PLAYER DATA =================
    basic = data.get("basicInfo", {})
    profile = data.get("profileInfo", {})
    clothes = profile.get("clothes") or []

    draw_tasks = {
        "mask":   clothes[0] if len(clothes) > 0 else None,
        "shirt":  clothes[1] if len(clothes) > 1 else None,
        "pants":  clothes[2] if len(clothes) > 2 else None,
        "shoes":  clothes[3] if len(clothes) > 3 else None,
        "emote":  clothes[4] if len(clothes) > 4 else None,
        "armor":  clothes[5] if len(clothes) > 5 else None,
        "weapon": (
            basic.get("weaponSkinShows", [None])[0]
            if basic.get("weaponSkinShows")
            else None
        ),
        "pet": data.get("petInfo", {}).get("skinId"),
        
        # FIXED: Prioritize equippedAnimationId exactly as requested
        "character": profile.get("equippedAnimationId") or profile.get("avatarId") or DEFAULT_ID
    }

    # ================= CHECK TEMPLATE =================
    if not os.path.exists(BACKGROUND_FILENAME):
        return jsonify({"error": "Background template not found"}), 500

    try:
        # ================= LOAD BACKGROUND =================
        canvas = Image.open(BACKGROUND_FILENAME).convert("RGBA")

        # ================= DRAW ITEMS =================
        for slot, item_id in draw_tasks.items():
            if not item_id:
                continue

            # ================= CHARACTER =================
            if slot == "character":
                icon_img = fetch_icon(item_id, size=CHARACTER_RENDER_SIZE, is_character=True)
                if not icon_img:
                    continue

                # CHARACTER HORIZONTALLY CENTERED, PERFECT STAGE FEET ALIGNMENT
                w, h = icon_img.size
                center_x = canvas.width // 2
                bottom_y = canvas.height - 25  # Adjusted ground padding
                pos = (int(center_x - w // 2), int(bottom_y - h))

            # ================= OTHER ITEMS =================
            else:
                icon_img = fetch_icon(item_id)
                if not icon_img:
                    continue
                pos = HEX_POSITIONS.get(slot)

            if not pos:
                continue

            canvas.paste(icon_img, pos, icon_img)

        # ================= SAVE =================
        img_io = BytesIO()
        canvas.save(img_io, format='PNG', optimize=True)
        img_io.seek(0)

        return send_file(
            img_io,
            mimetype='image/png',
            as_attachment=False,
            download_name=f"outfit_{uid}.png"
        )

    except Exception as e:
        return jsonify({"error": f"Image generation failed: {str(e)}"}), 500

# ================= ERRORS =================
@app.errorhandler(404)
def not_found(error):
    return jsonify({"error": "Endpoint not found"}), 404

@app.errorhandler(500)
def internal_error(error):
    return jsonify({"error": "Internal server error"}), 500

# ================= RUN =================
if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    debug = os.environ.get("DEBUG", "False").lower() == "true"
    app.run(host="0.0.0.0", port=port, debug=debug)
