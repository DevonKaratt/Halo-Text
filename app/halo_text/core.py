"""Pure geometry, grouping, change detection, and bounded translation cache."""
from collections import OrderedDict
from dataclasses import dataclass, field
import re
import cv2
import numpy as np

@dataclass(frozen=True)
class Box:
    x: int
    y: int
    w: int
    h: int

    @property
    def right(self): return self.x + self.w

    @property
    def bottom(self): return self.y + self.h

    def union(self, other):
        x, y = min(self.x, other.x), min(self.y, other.y)
        return Box(x, y, max(self.right, other.right)-x, max(self.bottom, other.bottom)-y)

    def clip(self, width, height):
        x, y = max(0, self.x), max(0, self.y)
        return Box(x, y, max(0, min(width, self.right)-x), max(0, min(height, self.bottom)-y))

@dataclass
class TextBlock:
    text: str
    box: Box
    confidence: float
    line_height: float
    lines: list[Box] = field(default_factory=list)
    background: tuple[int, int, int] = (255, 255, 255)

@dataclass
class Translation:
    block: TextBlock
    text: str

def normalize(text):
    return " ".join(text.split())

def is_english_candidate(text):
    text = normalize(text)
    if re.match(r"^(https?://|www\.)", text, re.I) or re.fullmatch(r"\S+@\S+\.\S+", text):
        return False
    letters = [ch for ch in text if ch.isalpha()]
    return len(letters) >= 2 and sum(ch.isascii() for ch in letters) / len(letters) >= 0.8

def group_lines(lines):
    """Merge adjacent, aligned body-text lines; avoid joining columns or headings."""
    groups = []
    for line in sorted(lines, key=lambda b: (b.box.y, b.box.x)):
        best = None
        for group in reversed(groups):
            last = group.lines[-1]
            gap = line.box.y - last.bottom
            aligned = abs(line.box.x - group.box.x) <= max(10, line.line_height * 0.6)
            same_size = 0.72 <= line.line_height / max(1, group.line_height) <= 1.4
            if (0 <= gap <= max(8, group.line_height * 0.7) and aligned and same_size
                    and len(group.lines) < 5 and len(group.text) + len(line.text) < 360):
                best = group
                break
        if best:
            best.text = normalize(best.text + " " + line.text)
            best.box = best.box.union(line.box)
            best.lines.append(line.box)
            best.confidence = min(best.confidence, line.confidence)
        else:
            groups.append(TextBlock(line.text, line.box, line.confidence,
                                    line.line_height, [line.box], line.background))
    return groups

def fingerprint(image):
    """Downsample moderately; retain local text changes, not just global brightness."""
    height, width = image.shape[:2]
    scale = min(1.0, 960 / width)
    gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
    return cv2.resize(gray, (max(1, round(width * scale)), max(1, round(height * scale))))

def frame_signature(image):
    return fingerprint(image)

def frames_differ(first, second):
    if first is None or second is None or first.shape != second.shape:
        return True
    changed = cv2.absdiff(first, second) > 24
    if changed.mean() > 0.0025:
        return True
    # Local changes (e.g. a menu label) must not be diluted by the whole screen.
    height, width = changed.shape
    tile = 24
    ph, pw = (-height) % tile, (-width) % tile
    padded = np.pad(changed, ((0, ph), (0, pw)), constant_values=False)
    tile_counts = padded.reshape(padded.shape[0]//tile, tile, padded.shape[1]//tile, tile).sum(axis=(1, 3))
    # Edge tiles may contain fewer real pixels. Dividing by padded area made
    # small caption changes near the bottom or right edge disappear.
    row_pixels = np.minimum(tile, height - np.arange(tile_counts.shape[0]) * tile)
    col_pixels = np.minimum(tile, width - np.arange(tile_counts.shape[1]) * tile)
    tile_changes = tile_counts / (row_pixels[:, None] * col_pixels[None, :])
    return bool(tile_changes.max(initial=0) > 0.09)

def sample_background(image, box):
    """Median border color in RGB, robust to a few dark glyph pixels."""
    height, width = image.shape[:2]
    b = Box(box.x-3, box.y-3, box.w+6, box.h+6).clip(width, height)
    if not b.w or not b.h:
        return (255, 255, 255)
    crop = image[b.y:b.bottom, b.x:b.right]
    border = np.concatenate((crop[:2].reshape(-1,3), crop[-2:].reshape(-1,3),
                             crop[:, :2].reshape(-1,3), crop[:, -2:].reshape(-1,3)))
    return tuple(int(x) for x in np.median(border, axis=0)[::-1])

class TranslationCache:
    """In-memory only: screen text is never written to disk."""
    def __init__(self, capacity=2000):
        self.capacity = capacity
        self.data = OrderedDict()

    def get(self, text):
        key = normalize(text)
        if key not in self.data:
            return None
        self.data.move_to_end(key)
        return self.data[key]

    def put(self, text, translation):
        key = normalize(text)
        self.data[key] = translation
        self.data.move_to_end(key)
        while len(self.data) > self.capacity:
            self.data.popitem(last=False)

def text_regions_differ(reference, current, boxes):
    """Check source text at full resolution, even when a change is tiny on a 4K screen."""
    if reference is None or not boxes:
        return False
    if reference.shape != current.shape:
        return True
    height, width = current.shape[:2]
    for box in boxes:
        b = Box(box.x-2,box.y-2,box.w+4,box.h+4).clip(width,height)
        if not b.w or not b.h:
            continue
        before = reference[b.y:b.bottom,b.x:b.right]
        after = current[b.y:b.bottom,b.x:b.right]
        mask = (cv2.absdiff(before,after).max(axis=2) > 24).astype(np.uint8)
        if int(mask.sum()) < 8:
            continue
        _, _, stats, _ = cv2.connectedComponentsWithStats(mask,8)
        for x,y,w,h,area in stats[1:]:
            # A thin blinking caret does not invalidate a whole paragraph.
            if area >= 8 and w >= 3 and h >= 3:
                return True
    return False
