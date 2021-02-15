import tornado.web, tornado.ioloop, tornado.websocket  
from picamera import PiCamera, PiVideoFrameType, Color # type: ignore # Tell PyLance to ignore import error
from string import Template
import io, os, socket, time
from io import BytesIO

# start configuration
serverPort = 8000

camera = PiCamera(sensor_mode=3, resolution='1014x760', framerate=0.5)
camera.vflip = True
camera.hflip = True
camera.video_denoise = True
camera.iso = 800
camera.shutter_speed = 2000000
camera.annotate_frame_num = True
camera.annotate_text_size = 12
camera.annotate_background = Color('black')

recordingOptions = {
    'format' : 'h264', 
    #'bitrate' : 25000000, 
    'quality' : 25, 
    'profile' : 'high', 
    'level' : '4.2', 
    'intra_period' : 15, 
    'intra_refresh' : 'both', 
    'inline_headers' : True, 
    'sps_timing' : True
}
# end configuration

s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
s.connect(('0.0.0.0', 0))
serverIp = s.getsockname()[0]
serverIp = 'myrpi3p35.local'

abspath = os.path.abspath(__file__)
dname = os.path.dirname(abspath)
os.chdir(dname)

def getFile(filePath):
    file = open(filePath,'r')
    content = file.read()
    file.close()
    return content

def templatize(content, replacements):
    tmpl = Template(content)
    return tmpl.substitute(replacements)

appHtml = templatize(getFile('index.html'), {'ip':serverIp, 'port':serverPort, 'fps':camera.framerate})
appJs = getFile('jmuxer.min.js')

class StreamBuffer(object):
    def __init__(self,camera):
        self.frameTypes = PiVideoFrameType()
        self.loop = None
        self.buffer = io.BytesIO()
        self.camera = camera
        self.time = time.time()

    def setLoop(self, loop):
        self.loop = loop

    def write(self, buf):
        if (time.time() - self.time) >= 1:
            self.time = time.time()
            self.camera.annotate_text = time.strftime("%m/%d/%Y %H:%M:%S", time.localtime())
        if self.camera.frame.complete and self.camera.frame.frame_type != self.frameTypes.sps_header:
            self.buffer.write(buf)
            if self.loop is not None and wsHandler.hasConnections():
                self.loop.add_callback(callback=wsHandler.broadcast, message=self.buffer.getvalue())
            self.buffer.seek(0)
            self.buffer.truncate()
        else:
            self.buffer.write(buf)

class wsHandler(tornado.websocket.WebSocketHandler):
    connections = []

    def open(self):
        self.connections.append(self)

    def on_close(self):
        self.connections.remove(self)

    def on_message(self, message):
        pass

    @classmethod
    def hasConnections(cl):
        if len(cl.connections) == 0:
            return False
        return True

    @classmethod
    async def broadcast(cl, message):
        for connection in cl.connections:
            try:
                await connection.write_message(message, True)
            except tornado.websocket.WebSocketClosedError:
                pass
            except tornado.iostream.StreamClosedError:
                pass

class htmlHandler(tornado.web.RequestHandler):
    def get(self):
        self.write(appHtml)

class jsHandler(tornado.web.RequestHandler):
    def get(self):
        self.write(appJs)

class captureHandler(tornado.web.RequestHandler):
    def get(self):
        myio = BytesIO()
        camera.capture(myio, use_video_port=True)
        myio.seek(0)
        self.write(getFile(myio))


requestHandlers = [
    (r"/ws/", wsHandler),
    (r"/", htmlHandler),
    (r"/jmuxer.min.js", jsHandler),
    (r"/capture.jpg", captureHandler)
]

try:
    streamBuffer = StreamBuffer(camera)
    camera.start_recording(streamBuffer, **recordingOptions) 
    application = tornado.web.Application(requestHandlers)
    application.listen(serverPort)
    loop = tornado.ioloop.IOLoop.current()
    streamBuffer.setLoop(loop)
    loop.start()
except KeyboardInterrupt:
    camera.stop_recording()
    camera.close()
    loop.stop() # type: ignore # Tell PyLance to suppress "possibly unbound" warning
