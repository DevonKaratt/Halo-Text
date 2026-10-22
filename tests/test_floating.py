import json
from types import SimpleNamespace
import pytest
from PySide6.QtCore import QPoint,QRect,QPointF,QEvent,Qt
from PySide6.QtGui import QContextMenuEvent,QMouseEvent
from PySide6.QtWidgets import QApplication
from halo_text.floating import FloatingHalo,clamp_position,SIZE

def make_icon(qapp,monkeypatch,tmp_path):
    monkeypatch.setattr("halo_text.floating.exclude_from_capture",lambda handle:True)
    return FloatingHalo(qapp,tmp_path/"floating.json")

def test_clamp_respects_negative_monitor_origin():
    areas=[QRect(-1920,0,1920,1080),QRect(0,0,1280,720)]
    assert clamp_position(QPoint(-2100,100),areas)==QPoint(-1920,100)
    assert clamp_position(QPoint(-500,100),areas)==QPoint(-500,100)
    assert clamp_position(QPoint(3000,900),areas)==QPoint(1280-SIZE,720-SIZE)

def test_clamp_recovers_position_after_monitor_disconnect():
    result=clamp_position(QPoint(-1600,-900),[QRect(0,0,1280,720)])
    assert result==QPoint(0,0)

@pytest.mark.parametrize("content",["invalid json","[]",'{"x":true,"y":"bad"}'])
def test_bad_position_file_does_not_break_startup(qapp,monkeypatch,tmp_path,content):
    path=tmp_path/"floating.json"
    path.write_text(content)
    icon=make_icon(qapp,monkeypatch,tmp_path)
    try:
        assert any(area.contains(icon.geometry()) for area in icon.areas())
    finally:
        icon.close()

def test_drag_moves_icon_and_remembers_position(qapp,monkeypatch,tmp_path):
    icon=make_icon(qapp,monkeypatch,tmp_path)
    icon.move(100,100)
    icon.show()
    start=icon.pos()
    local=QPointF(34,34)
    global_start=QPointF(icon.mapToGlobal(QPoint(34,34)))
    def send(kind,global_pos,button,buttons):
        event=QMouseEvent(kind,local,global_pos,button,buttons,Qt.KeyboardModifier.NoModifier)
        QApplication.sendEvent(icon,event)
    try:
        send(QEvent.Type.MouseButtonPress,global_start,Qt.MouseButton.LeftButton,Qt.MouseButton.LeftButton)
        send(QEvent.Type.MouseMove,global_start+QPointF(80,40),Qt.MouseButton.NoButton,Qt.MouseButton.LeftButton)
        send(QEvent.Type.MouseButtonRelease,global_start+QPointF(80,40),Qt.MouseButton.LeftButton,Qt.MouseButton.NoButton)
        assert icon.pos()==start+QPoint(80,40)
        saved=json.loads((tmp_path/"floating.json").read_text())
        assert saved=={"x":icon.x(),"y":icon.y()}
    finally:
        icon.close()
    restored=make_icon(qapp,monkeypatch,tmp_path)
    try:
        assert restored.pos()==start+QPoint(80,40)
    finally:
        restored.close()

def test_right_click_requests_controls_at_pointer(qapp,monkeypatch,tmp_path):
    icon=make_icon(qapp,monkeypatch,tmp_path)
    seen=[]
    icon.controls_requested.connect(seen.append)
    try:
        point=icon.mapToGlobal(QPoint(34,34))
        event=QContextMenuEvent(QContextMenuEvent.Reason.Mouse,QPoint(34,34),point)
        QApplication.sendEvent(icon,event)
        assert seen==[point]
    finally:
        icon.close()

def test_capture_exclusion_failure_hides_icon(qapp,monkeypatch,tmp_path):
    monkeypatch.setattr("halo_text.floating.exclude_from_capture",lambda handle:False)
    icon=FloatingHalo(qapp,tmp_path/"floating.json")
    try:
        icon.show()
        assert not icon.excluded and not icon.isVisible()
    finally:
        icon.close()

def test_nested_control_panels_pause_once_and_resume_after_last_close():
    from halo_text.app import Controller
    calls=[]
    state=SimpleNamespace(controls_depth=0,resume_after_controls=False,
        overlay=SimpleNamespace(items=[object()]),busy=False,wanted=False,
        region=object(),ready=True,selector=None,exiting=False,
        invalidate=lambda:calls.append("invalidate"))
    Controller.begin_controls(state)
    Controller.begin_controls(state)
    assert state.controls_depth==2 and calls==["invalidate"]
    Controller.end_controls(state)
    assert state.controls_depth==1 and not state.wanted
    Controller.end_controls(state)
    assert state.controls_depth==0 and state.wanted

def test_completed_translation_cannot_paint_over_controls():
    from halo_text.app import Controller
    state=SimpleNamespace(busy=True,exiting=False,generation=2,selector=None,
        controls_depth=1,job_frame=object(),ready=True,auto=False,status=lambda *a,**k:None)
    Controller.finished(state,2,SimpleNamespace(translations=[]))
    assert not state.busy and state.job_frame is None
