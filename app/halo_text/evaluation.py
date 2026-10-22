"""Repeatable labeled synthetic screens; complements real-app acceptance tests."""
import json
import os
from time import perf_counter
from .paths import ROOT
from .core import Box, normalize
from .demo import edit_distance, image_array

CASES = [
    ("light_document",24,"#ffffff","#172033",1.0,[
        ("Please read the instructions carefully.",40,80),
        ("The meeting will start tomorrow morning.",40,150),
        ("Save your work before closing the window.",40,220)]),
    ("dark_document",22,"#111827","#f3f4f6",1.0,[
        ("Technology helps people communicate.",40,80),
        ("Education is important for everyone.",40,150),
        ("Students can learn new skills every day.",40,220)]),
    ("small_text",13,"#ffffff","#202020",1.0,[
        ("Please check your internet connection.",40,70),
        ("Your changes have been saved successfully.",40,110),
        ("The next meeting is scheduled for Monday.",40,150)]),
    ("interface_labels",15,"#f1f5f9","#172033",1.0,[
        ("Open file",40,70),("Save changes",40,120),
        ("Search documents",40,170),("Network settings",40,220)]),
    ("two_columns",18,"#ffffff","#202020",1.0,[
        ("Students can learn new skills.",40,70),
        ("Please read the instructions.",500,70),
        ("Education is important.",40,115),
        ("Save your work before closing.",500,115),
        ("The meeting starts tomorrow.",40,190),
        ("Click here to continue.",500,190)]),
    ("low_contrast",18,"#edf2f7","#929eae",1.0,[
        ("Please read the instructions carefully.",40,70),
        ("The meeting will start tomorrow morning.",40,130),
        ("Save your work before closing the window.",40,190)]),
    ("scaled_150_percent",20,"#ffffff","#172033",1.5,[
        ("Welcome to our project.",40,70),
        ("Technology helps people communicate.",40,130),
        ("This application translates English into Hindi.",40,190)]),
    ("blank_screen",20,"#ffffff","#172033",1.0,[]),
]

def intersection_over_union(a,b):
    intersection=max(0,min(a.right,b.right)-max(a.x,b.x))*max(0,min(a.bottom,b.bottom)-max(a.y,b.y))
    union=a.w*a.h+b.w*b.h-intersection
    return intersection/union if union else 0.0

def recognition_metrics(expected,observed):
    remaining=list(observed)
    errors=0
    characters=0
    matched=0
    for text,box in expected:
        reference=normalize(text).casefold()
        characters+=len(reference)
        index=max(range(len(remaining)),key=lambda i:intersection_over_union(box,remaining[i].box),default=None)
        if index is not None and intersection_over_union(box,remaining[index].box)>=0.15:
            block=remaining.pop(index)
            hypothesis=normalize(block.text).casefold()
            matched+=1
        else:
            hypothesis=""
        errors+=edit_distance(reference,hypothesis)
    errors+=sum(len(normalize(block.text)) for block in remaining)
    return {"expected_lines":len(expected),"matched_lines":matched,"extra_lines":len(remaining),
            "character_errors":errors,"reference_characters":characters,
            "character_error_rate":round(errors/characters,4) if characters else None}

def draw_case(case):
    from PySide6.QtGui import QImage,QColor,QPainter,QFont,QFontMetrics
    name,size,background,foreground,scale,lines=case
    image=QImage(round(1000*scale),round(300*scale),QImage.Format.Format_RGB32)
    image.fill(QColor(background))
    painter=QPainter(image)
    painter.scale(scale,scale)
    font=QFont("Segoe UI")
    font.setPixelSize(size)
    painter.setFont(font)
    painter.setPen(QColor(foreground))
    metrics=QFontMetrics(font)
    expected=[]
    for text,x,y in lines:
        painter.drawText(x,y,text)
        rect=metrics.tightBoundingRect(text)
        expected.append((text,Box(round((x+rect.x())*scale),round((y+rect.y())*scale),
                                  round(rect.width()*scale),round(rect.height()*scale))))
    painter.end()
    return image,expected

def main(config=None):
    os.environ.setdefault("QT_QPA_PLATFORM","offscreen")
    from PySide6.QtWidgets import QApplication
    from PySide6.QtGui import QPainter
    from .fonts import load_fonts
    from .config import load_config
    from .pipeline import Pipeline
    from .overlay import prepare_paint_blocks,paint_blocks
    app=QApplication.instance() or QApplication([])
    load_fonts()
    config=config or load_config()
    from .languages import language
    target_name=language(config.target).name
    pipeline=Pipeline(config)
    pipeline.warmup()
    folder=ROOT/"reports"/"evaluation"
    if config.target != "hi":
        folder=folder/config.target
    folder.mkdir(parents=True,exist_ok=True)
    records=[]
    for case in CASES:
        name,_,_,_,scale,_=case
        source,expected=draw_case(case)
        frame=image_array(source)
        lines=pipeline.ocr.recognize_lines(frame)
        metrics=recognition_metrics(expected,lines)
        result=pipeline.process(frame)
        items,skipped=prepare_paint_blocks(result.translations,config,scale,scale)
        preview=source.copy()
        painter=QPainter(preview)
        painter.scale(scale,scale)
        paint_blocks(painter,items)
        painter.end()
        source.save(str(folder/(name+"_english.png")))
        preview.save(str(folder/(name+"_"+target_name.lower()+".png")))
        record=dict(case=name,**metrics,**result.metrics,displayed_blocks=len(items),skipped_blocks=skipped,
                    translations=[{"english":item.block.text,"translated":item.text} for item in result.translations])
        records.append(record)
        print(json.dumps({k:v for k,v in record.items() if k!="translations"}),flush=True)
    report={"scope":"Labeled generated screens, not a representative real-world dataset",
            "backend":config.backend,"target":config.target,"font":language(config.target).font,
            "timing":"Warm models; OCR plus translation only, excluding capture and settle delay",
            "cases":records}
    (folder/"results.json").write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding="utf-8")
    rows=["# HALO TEXT evaluation","",
          "These are generated, labeled screens. They test layout and pipeline behavior; they do not establish real-world accuracy or human translation quality.","",
          f"| Case | Lines matched | OCR character error | {target_name} blocks displayed | Blocks skipped | Processing |",
          "|---|---:|---:|---:|---:|---:|"]
    for r in records:
        cer="n/a" if r["character_error_rate"] is None else f'{r["character_error_rate"]:.1%}'
        rows.append(f'| {r["case"]} | {r["matched_lines"]}/{r["expected_lines"]} | {cer} | {r["displayed_blocks"]} | {r["skipped_blocks"]} | {r["total_ms"]/1000:.2f}s |')
    rows += ["","Metrics use one-to-one matching of detected lines to labeled text positions. Missing and extra text count as character errors. Case and whitespace are normalized.",
             "The 150% case is a generated scaling test, not a change to the Windows display settings.",
             "Timings use already-loaded models. Repeated sentences may use the translation cache.",
             "Generated inputs, translated previews, recognized text and translations are saved under reports/evaluation/.",
             "Review meaning with a fluent speaker before claiming translation accuracy.",""]
    (folder/("EVALUATION.md" if config.target=="hi" else f"EVALUATION_{config.target}.md")).write_text("\n".join(rows),encoding="utf-8")
    return 0
