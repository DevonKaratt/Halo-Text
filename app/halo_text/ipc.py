"""Per-user local named pipe for status and graceful lifecycle commands."""
import hashlib
import json
from PySide6.QtCore import QCoreApplication, QObject, QTimer
from PySide6.QtNetwork import QLocalServer, QLocalSocket
from .paths import ROOT

SERVER_NAME = "halo-text-" + hashlib.sha256(str(ROOT).casefold().encode()).hexdigest()[:20]
COMMANDS = {"status", "stop", "clear", "activate", "original", "audio-stop"}

def request(command, name=SERVER_NAME, timeout=2000):
    if command not in COMMANDS:
        raise ValueError("Unsupported control command")
    application = QCoreApplication.instance() or QCoreApplication([])
    socket = QLocalSocket()
    socket.connectToServer(name)
    if not socket.waitForConnected(timeout):
        return {"running": False, "message": "HALO TEXT is not running."}
    socket.write((command+"\n").encode("ascii"))
    socket.flush()
    if not socket.canReadLine() and not socket.waitForReadyRead(timeout):
        socket.abort()
        raise RuntimeError("HALO TEXT did not answer the control request.")
    data = bytes(socket.readAll())
    while b"\n" not in data and len(data) < 8192:
        if not socket.waitForReadyRead(timeout):
            break
        data += bytes(socket.readAll())
    socket.disconnectFromServer()
    if len(data) > 8192 or b"\n" not in data:
        raise RuntimeError("Incomplete control response.")
    return json.loads(data.split(b"\n",1)[0])

class CommandServer(QObject):
    def __init__(self, callback, name=SERVER_NAME, parent=None):
        super().__init__(parent)
        self.callback = callback
        self.server = QLocalServer(self)
        self.server.setSocketOptions(QLocalServer.SocketOption.UserAccessOption)
        self.server.newConnection.connect(self.accept)
        if not self.server.listen(name):
            raise RuntimeError("Could not open HALO TEXT's local control channel.")

    def accept(self):
        while self.server.hasPendingConnections():
            socket = self.server.nextPendingConnection()
            socket.disconnected.connect(socket.deleteLater)
            timer = QTimer(socket)
            timer.setSingleShot(True)
            timer.timeout.connect(socket.abort)
            timer.start(2000)
            def receive(s=socket, t=timer):
                if s.bytesAvailable() > 64:
                    s.abort()
                    return
                if not s.canReadLine():
                    return
                command = bytes(s.readLine()).decode("ascii",errors="replace").strip()
                result = (self.callback(command) if command in COMMANDS
                          else {"error":"Unsupported command"})
                t.stop()
                s.write((json.dumps(result,ensure_ascii=True)+"\n").encode())
                s.flush()
                s.disconnectFromServer()
            socket.readyRead.connect(receive)
            receive()

    def close(self):
        self.server.close()
