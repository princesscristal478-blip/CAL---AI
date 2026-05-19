"""
generate_icons.py — Generate all required PWA icons
Run: python generate_icons.py
Requires: Pillow (pip install Pillow)
"""
from PIL import Image, ImageDraw, ImageFont
import os

SIZES = [72, 96, 128, 144, 152, 192, 384, 512]
OUT_DIR = os.path.join(os.path.dirname(__file__), 'static', 'icons')
os.makedirs(OUT_DIR, exist_ok=True)

def make_icon(size):
    img = Image.new('RGBA', (size, size), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)

    # Background circle
    pad = size * 0.05
    draw.ellipse([pad, pad, size - pad, size - pad], fill=(34, 197, 94, 255))

    # Inner lighter circle
    pad2 = size * 0.15
    draw.ellipse([pad2, pad2, size - pad2, size - pad2], fill=(22, 163, 74, 255))

    # Emoji / text
    emoji = "🥗"
    font_size = int(size * 0.45)
    try:
        # Try system emoji font
        font = ImageFont.truetype("/usr/share/fonts/truetype/noto/NotoColorEmoji.ttf", font_size)
    except:
        try:
            font = ImageFont.truetype("/System/Library/Fonts/Apple Color Emoji.ttc", font_size)
        except:
            font = ImageFont.load_default()

    # Draw emoji centered
    try:
        bbox = draw.textbbox((0, 0), emoji, font=font)
        w = bbox[2] - bbox[0]
        h = bbox[3] - bbox[1]
        x = (size - w) // 2
        y = (size - h) // 2
        draw.text((x, y), emoji, font=font, embedded_color=True)
    except:
        # Fallback: draw "CA" text
        draw.text((size*0.25, size*0.28), "CA", fill=(255,255,255,255))

    path = os.path.join(OUT_DIR, f'icon-{size}.png')
    img.save(path, 'PNG')
    print(f'  ✓ icon-{size}.png')

print('Generating PWA icons...')
for size in SIZES:
    make_icon(size)
print(f'Done! Icons saved to {OUT_DIR}')
