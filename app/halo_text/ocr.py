import cv2
from .core import Box, TextBlock, group_lines, is_english_candidate, normalize, sample_background
from .ocr_packs import PACKS, installed, engine as pack_engine
from .source_language import detect, script_match

class ScreenOCR:
    def __init__(self, config):
        from rapidocr import RapidOCR
        self.config = config
        self.engine = RapidOCR(params={
            "Global.log_level": "warning",
            "Global.use_cls": False,
            "Det.limit_type": "max",
            "Det.limit_side_len": config.max_image_edge,
            "EngineConfig.onnxruntime.intra_op_num_threads": config.cpu_threads,
            "EngineConfig.onnxruntime.inter_op_num_threads": 1,
        })
        self.pack_engines = {}
        self.last_source = "en"

    def reload_packs(self):
        active = {key for key in PACKS if installed(key)}
        self.pack_engines = {key: value for key, value in self.pack_engines.items() if key in active}

    def recognize_lines(self, image, fast_captions=False, engine=None, pack=None):
        engine = engine or self.engine
        height, width = image.shape[:2]
        # Caption strips do not need the library's document-oriented vertical padding.
        # Keep tiny crops and page-shaped selections on the existing safe path.
        caption_strip = fast_captions and 48 <= height <= 240 and width >= height*2
        edge = min(self.config.max_image_edge,960) if caption_strip else self.config.max_image_edge
        scale = min(1.0, edge / max(height, width))
        scaled = cv2.resize(image, None, fx=scale, fy=scale) if scale != 1 else image
        padding = engine.cfg.Global.use_vertical_padding
        try:
            if caption_strip:
                engine.cfg.Global.use_vertical_padding = False
            output = engine(scaled, use_det=True, use_cls=False, use_rec=True)
        finally:
            engine.cfg.Global.use_vertical_padding = padding
        if output.boxes is None or output.txts is None:
            return []
        lines = []
        for points, text, confidence in zip(output.boxes, output.txts, output.scores):
            text = normalize(text)
            valid = script_match(text, pack) >= .55 if pack else is_english_candidate(text)
            if confidence < self.config.ocr_confidence or not valid:
                continue
            left, top = points.min(axis=0) / scale
            right, bottom = points.max(axis=0) / scale
            box = Box(round(left), round(top), round(right-left), round(bottom-top)).clip(width, height)
            if box.w < 4 or box.h < 5:
                continue
            lines.append(TextBlock(text, box, float(confidence), box.h))
        return lines

    def recognize(self, image, fast_captions=False):
        self.source_confident = False
        override=getattr(self.config,"input_language","auto")
        if override!="auto":
            from .ocr_packs import LANGUAGE_PACK
            pack=LANGUAGE_PACK.get(override)
            if pack and installed(pack):
                if pack not in self.pack_engines:
                    self.pack_engines[pack]=pack_engine(pack,self.config)
                lines=self.recognize_lines(image,fast_captions,self.pack_engines[pack],pack)
                self.last_pack=pack
            elif override=="en":
                lines=self.recognize_lines(image,fast_captions=fast_captions)
                self.last_pack=None
            else:
                raise RuntimeError("Selected input OCR pack is not installed")
            self.last_source=override
            blocks=group_lines(lines)
            for block in blocks:
                block.background=sample_background(image,block.box)
            return blocks[:self.config.max_blocks]
        available = [key for key in PACKS if installed(key)]
        previous = getattr(self,"last_pack",None)
        if previous in available and previous != "latin":
            if previous not in self.pack_engines:
                self.pack_engines[previous] = pack_engine(previous,self.config)
            preferred = self.recognize_lines(image,fast_captions,self.pack_engines[previous],previous)
            if preferred and sum(script_match(line.text,previous) for line in preferred)/len(preferred) >= .8:
                lines=preferred
                self.last_source=detect(" ".join(line.text for line in lines))
                blocks=group_lines(lines)
                for block in blocks:
                    block.background=sample_background(image,block.box)
                return blocks[:self.config.max_blocks]
        lines = self.recognize_lines(image,fast_captions=fast_captions)
        english_text=" ".join(line.text for line in lines)
        if (len(english_text)>=8 and lines
                and sum(line.confidence for line in lines)/len(lines)>=.88
                and detect(english_text)=="en"):
            self.source_confident=True
            self.last_pack=None
            self.last_source="en"
            blocks=group_lines(lines)
            for block in blocks:
                block.background=sample_background(image,block.box)
            return blocks[:self.config.max_blocks]
        best = lines
        best_score = sum(line.confidence * len(line.text) for line in lines)
        # Previously identified script first; users usually keep one source in a caption area.
        available.sort(key=lambda key: key != getattr(self, "last_pack", None))
        chosen_pack = None
        for key in available:
            if key not in self.pack_engines:
                self.pack_engines[key] = pack_engine(key, self.config)
            candidate = self.recognize_lines(image, fast_captions, self.pack_engines[key], key)
            score = sum(line.confidence * len(line.text) * script_match(line.text, key) for line in candidate)
            threshold=1.1 if key=="latin" else 1.4
            if score > best_score * threshold and candidate:
                best, best_score, chosen_pack = candidate, score, key
        lines = best
        self.last_pack = chosen_pack
        self.last_source = detect(" ".join(line.text for line in lines))
        blocks = group_lines(lines)
        for block in blocks:
            block.background = sample_background(image, block.box)
        return blocks[:self.config.max_blocks]
