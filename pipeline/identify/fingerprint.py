"""Fingerprint of a page image: CLIP ViT-L/14 over the whole page and its four quarters, concatenated.
Any change to this file changes CODE_HASH, and `survey train` must rerun."""
import hashlib
from functools import lru_cache
from importlib.metadata import version
from pathlib import Path

import numpy as np
from PIL import Image, ImageOps

MODEL_ID = "openai/clip-vit-large-patch14"
REVISION = "32bd64288804d66eefd0ccbe215aa642df71cc41"
NORM = ([0.4815, 0.4578, 0.4082], [0.2686, 0.2613, 0.2758])   # CLIP's training statistics
SIZE = 224                                                     # what the backbone sees, per view
TILE_RENDER = (728, 448)                                       # landscape render the quarters are cut from
BATCH = 16

CODE_HASH = hashlib.sha1(Path(__file__).read_bytes().replace(b"\r\n", b"\n")
                         + f"{version('torch').split('+')[0]} {version('transformers')}".encode()).hexdigest()[:12]


def fingerprint(paths: list[Path]) -> np.ndarray:
    """(N, D) float32, one row per image."""
    if not paths:
        return np.zeros((0, 0), np.float32)
    w, h = TILE_RENDER
    views = []
    for p in paths:
        tiles = _view(p, TILE_RENDER)
        views.append(_view(p, (SIZE, SIZE)))
        views += [tiles.crop((x, y, x + w // 2, y + h // 2)).resize((SIZE, SIZE), Image.BILINEAR)
                  for y in (0, h // 2) for x in (0, w // 2)]
    return _clip(views).reshape(len(paths), -1)


def _view(path: Path, size: tuple[int, int]) -> Image.Image:
    im = Image.open(path)
    im.draft("L", (size[0] * 2, size[1] * 2))
    return ImageOps.grayscale(im).resize(size, Image.BILINEAR)


@lru_cache(maxsize=1)
def _backbone():
    import torch
    from transformers import AutoModel
    device = "cuda" if torch.cuda.is_available() else "cpu"
    return AutoModel.from_pretrained(MODEL_ID, revision=REVISION).vision_model.to(device).eval(), device


def _clip(images: list[Image.Image]) -> np.ndarray:
    """(N, D) per image: [first token ; mean of the other tokens]."""
    import torch
    model, device = _backbone()
    mean, std = (np.array(v, np.float32)[:, None, None] for v in NORM)
    out = []
    with torch.no_grad():
        for i in range(0, len(images), BATCH):
            x = np.stack([(np.asarray(im.convert("RGB"), np.float32).transpose(2, 0, 1) / 255 - mean) / std
                          for im in images[i:i + BATCH]])
            h = model(pixel_values=torch.from_numpy(x).to(device)).last_hidden_state
            out.append(torch.cat([h[:, 0], h[:, 1:].mean(1)], 1).float().cpu().numpy())
    return np.concatenate(out)
