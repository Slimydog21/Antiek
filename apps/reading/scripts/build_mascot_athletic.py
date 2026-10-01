"""Prepare the approved Krea B raster family, without runtime color filters.

Run from any directory using Pillow, NumPy and SciPy in the art-tool environment.
No API calls, paid jobs or secrets are used by this reproducible packaging step.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageFilter
from scipy import ndimage

APP = Path(__file__).resolve().parents[1]
BRAND = APP / 'src/brand'
EVIDENCE = APP.parents[1] / 'docs/evidence/reading-comfort-20261001/krea-athletic'
OUT = BRAND / 'mascot-brain/athletic'
MAGENTA = (148, 61, 74)
SOURCES = {
    'idle': 'mascot-brain/01_hero_front_transparent.png',
    'blink': 'mascot-brain/blink_closed_transparent.png',
    'thinking': 'mascot-brain/mood_thinking.png',
    'empty': 'mascot-brain/mood_sleepy.png',
    'celebrate': 'mascot-brain/mood_excited.png',
    'headTilt': 'mascot-brain/authored/mascot_head_tilt_v1_transparent.png',
    'sleeping': 'mascot-brain/authored/mascot_sleeping_v1_transparent.png',
    **{name: f'workflow-art/{name}-512.png' for name in (
        'read', 'research', 'speak', 'biography', 'library', 'wrestler',
        'outcomes', 'interviews', 'notebooks', 'sources', 'pricing', 'trust')},
    'write': 'workflow-art/write-hands-20261001.png',
}
NAMES = {
    'idle': '01_hero_front_b_20261001.png',
    'blink': 'blink_closed_b_20261001.png',
    'thinking': 'mood_thinking_b_20261001.png',
    'empty': 'mood_sleepy_b_20261001.png',
    'celebrate': 'mood_excited_b_20261001.png',
    'headTilt': 'authored/mascot_head_tilt_v1_transparent.png',
    'sleeping': 'authored/mascot_sleeping_v1_transparent.png',
}


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def approved_anchor() -> Image.Image:
    anchor = Image.open(EVIDENCE / 'h-b-magenta-court.png').convert('RGBA')
    wordmark = Image.open(EVIDENCE / 'k-b-integrated-bold.png').convert('RGBA')
    # The operator approved this integrated lettering and the ORIGINAL B shoes.
    # Import only the edited cloth/lettering region. No shoe pixel is replaced.
    region = (345, 326, 532, 389)
    anchor.paste(wordmark.crop(region), region[:2])
    return anchor


def blink_anchor(anchor: Image.Image) -> Image.Image:
    closed = Image.open(EVIDENCE / 'poses/blink-krea-b.png').convert('RGBA')
    result = anchor.copy()
    mask = Image.new('L', anchor.size)
    draw = ImageDraw.Draw(mask)
    for box in [(340, 432, 389, 485), (463, 432, 515, 485)]:
        draw.ellipse(box, fill=255)
    mask = mask.filter(ImageFilter.GaussianBlur(2))
    result.paste(closed, (0, 0), mask)
    return result


def material_color(image: Image.Image) -> tuple[Image.Image, int]:
    a = np.array(image.convert('RGBA'))
    r, g, b = (a[:, :, i].astype(float) for i in range(3))
    material = (r > g * 1.3) & (b > g + 5) & (r < 210) & (g < 125)
    a[material, :3] = MAGENTA
    return Image.fromarray(a), int(material.sum())


def matte(image: Image.Image) -> Image.Image:
    a = np.array(image.convert('RGBA'))
    background = np.linalg.norm(a[:, :, :3].astype(float) - [252, 239, 221], axis=2) < 46
    labels, _ = ndimage.label(background)
    ids = set(labels[0]) | set(labels[-1]) | set(labels[:, 0]) | set(labels[:, -1])
    ids.discard(0)
    # Remove the enclosed negative space between the legs. Cream toe/sole,
    # paper and book covers remain opaque inside their illustrated outlines.
    h, w = background.shape
    for ident, slices in enumerate(ndimage.find_objects(labels), 1):
        if slices is None or ident in ids:
            continue
        y, x = slices
        if (y.start > h * .55 and y.stop > h * .72 and
                y.stop - y.start > h * .095 and x.start > w * .38 and
                x.stop < w * .64 and x.stop - x.start < w * .15):
            ids.add(ident)
    a[np.isin(labels, list(ids))] = (0, 0, 0, 0)
    return Image.fromarray(a)


def build() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    anchor = approved_anchor()
    records = []
    for name, original in SOURCES.items():
        source = BRAND / original
        if name in ('idle', 'blink', 'headTilt'):
            raw = blink_anchor(anchor) if name == 'blink' else anchor.copy()
            inputs = [EVIDENCE / 'h-b-magenta-court.png', EVIDENCE / 'k-b-integrated-bold.png']
            if name == 'blink':
                inputs.append(EVIDENCE / 'poses/blink-krea-b.png')
        else:
            folder = 'poses-corrections' if name in ('thinking', 'celebrate') else 'poses'
            input_path = EVIDENCE / folder / (name + '-krea-b.png')
            raw = Image.open(input_path).convert('RGBA')
            inputs = [input_path]
        colored, corrected = material_color(raw)
        result = matte(colored)
        if name == 'headTilt':
            result = result.rotate(-5, resample=Image.Resampling.BICUBIC)
            result, _ = material_color(result)
        original_image = Image.open(source).convert('RGBA')
        target = (512, 512) if name == 'write' else original_image.size
        original_bounds = original_image.getbbox()
        bounds = result.getbbox()
        if original_bounds is None or bounds is None:
            raise ValueError(f'{name}: empty artwork')
        sx, sy = target[0] / original_image.width, target[1] / original_image.height
        left, top, right, bottom = original_bounds
        desired = (left * sx, top * sy, right * sx, bottom * sy)
        cropped = result.crop(bounds)
        scale = min((desired[2] - desired[0]) / cropped.width,
                    (desired[3] - desired[1]) / cropped.height)
        artwork = cropped.resize((round(cropped.width * scale), round(cropped.height * scale)),
                                 Image.Resampling.LANCZOS)
        result = Image.new('RGBA', target)
        x = round((desired[0] + desired[2] - artwork.width) / 2)
        y = round((desired[1] + desired[3] - artwork.height) / 2)
        result.alpha_composite(artwork, (x, y))
        result, _ = material_color(result)
        destination = OUT / NAMES.get(name, name + '-b-20261001.png')
        destination.parent.mkdir(parents=True, exist_ok=True)
        result.save(destination, optimize=True)
        final = np.array(result)
        exact = np.all(final[:, :, :3] == MAGENTA, axis=2) & (final[:, :, 3] == 255)
        count = int(exact.sum())
        if count < 100 or final[0, 0, 3] != 0:
            raise ValueError(f'{name}: invalid magenta material or outer matte')
        records.append({
            'pose': name, 'original_source': original, 'original_sha256': sha(source),
            'inputs': [{'file': str(p.relative_to(EVIDENCE)), 'sha256': sha(p)} for p in inputs],
            'output': str(destination.relative_to(OUT)), 'output_sha256': sha(destination),
            'size': list(target), 'bytes': destination.stat().st_size,
            'magenta_material_pixels_corrected': corrected, 'exact_magenta_pixels': count,
        })
        print(name, destination.stat().st_size, 'bytes; exact magenta', count)
    provenance = {
        'label': 'ai-generated', 'provider': 'Krea API', 'model': 'google/nano-banana-pro',
        'approved_colorway_job': 'ab887cec-2b86-43da-b004-7e32e57fa7fa',
        'integrated_wordmark_job': 'd69e1cd7-3680-4076-bb22-c89459bcc189',
        'operator_approval': 'I like it! on 2026-10-01, after restoring integrated lettering and original B shoes',
        'magenta': '#943D4A', 'rgb': list(MAGENTA),
        'typography': 'Image-integrated bold lettering inspired by Inter/Source Serif 4; no text or glyph overlay',
        'method': 'Krea reference edits retain the pose roles and props. Local preparation fixes material RGB and removes background. Idle retains original B shoes; blink changes only eye regions; authored tilt rotates the approved anchor 5 degrees. Each full pose is uniformly scaled to its original optical bounds without distorting shoe proportions.',
        'original_assets_retained': True, 'poses': records,
    }
    (OUT / 'provenance.json').write_text(json.dumps(provenance, indent=2) + '\n')


if __name__ == '__main__':
    build()
