import socket
import network
import utime
from machine import Pin, PWM, Timer, disable_irq, enable_irq

led = Pin("LED", Pin.OUT)
led.high()

class Motor():
    FREQ = 20000

    def __init__(self, p1, p2, forward_duty_ns, backward_duty_ns):
        self.p1 = PWM(Pin(p1, Pin.OUT))
        self.p2 = PWM(Pin(p2, Pin.OUT))
        self.p1.freq(self.FREQ)
        self.p2.freq(self.FREQ)
        self.forward_duty_ns = forward_duty_ns
        self.backward_duty_ns = backward_duty_ns

    def stop(self):
        self.p1.duty_ns(0)
        self.p2.duty_ns(0)

    def forward(self):
        self.stop()
        self.p1.duty_ns(self.forward_duty_ns)
        self.p2.duty_ns(0)

    def backward(self):
        self.stop()
        self.p1.duty_ns(0)
        self.p2.duty_ns(self.backward_duty_ns)


class Direction():
    NONE = 0
    FORWARD = 1
    BACKWARD = 2
    LEFT_ROTATION = 4
    RIGHT_ROTATION = 8


class Movement():
    def __init__(self):
        self.mleft = Motor(10, 12, 15450, 15450)
        self.mright = Motor(19, 21, 14500, 14500)
        self.direction = Direction.NONE
        self.timer = None
        self.timestamp_ms = 0

    def forward(self):
        if self.direction != Direction.FORWARD:
            self.stop()
        self.direction = Direction.FORWARD
        self.mleft.forward()
        self.mright.forward()
        self.timer_init()

    def backward(self):
        if self.direction != Direction.BACKWARD:
            self.stop()
        self.direction = Direction.BACKWARD
        self.mleft.backward()
        self.mright.backward()
        self.timer_init()

    def left_rotation(self):
        if self.direction != Direction.LEFT_ROTATION:
            self.stop()
        self.direction = Direction.LEFT_ROTATION
        self.mleft.backward()
        self.mright.forward()
        self.timer_init(500)

    def right_rotation(self):
        if self.direction != Direction.RIGHT_ROTATION:
            self.stop()
        self.direction = Direction.RIGHT_ROTATION
        self.mleft.forward()
        self.mright.backward()
        self.timer_init(500)

    def stop(self):
        self.mleft.stop()
        self.mright.stop()
        if self.timer:
            self.timer.deinit()
            self.timer = None

    def timer_init(self, inactive_movement_stop_ms=1000):
        if self.timer:
            self.timer.deinit()
        self.timestamp_ms = utime.ticks_ms()
        self.timer = Timer(period=100, callback=lambda _: self.timer_callback(inactive_movement_stop_ms))

    def timer_callback(self, inactive_movement_stop_ms):
        timestamp = utime.ticks_ms()
        # critical section
        irq = disable_irq()
        if self.timestamp_ms + inactive_movement_stop_ms <= timestamp:
            self.stop()
        enable_irq(irq)


movement = Movement()


# Listens on 192.168.4.1
wlan = network.WLAN(network.AP_IF)
wlan.config(essid="xxx", password="xpasswordx")
wlan.active(True)


class PicoHttpServer():
    def __init__(self):
        self.methods = {}

    def register_method(self, path, method):
        self.methods[path] = method

    @staticmethod
    def get_path_from_request(req):
        req = req.lstrip("GET ")
        path_end = req.find(" ")
        return req[:(path_end if path_end >= 0 else len(req))]

    @staticmethod
    def send_response(cl, status, msg=""):
        cl.send(f"HTTP/1.1 {status}\r\nContent-Type: text/html\r\n\r\n")
        cl.send(msg.encode())
        cl.close()

    def run(self):
        addr = socket.getaddrinfo('0.0.0.0', 80)[0][-1]
        sock = socket.socket()
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        sock.bind(addr)
        sock.listen(1)

        print(f"running server on {addr}:80")
        try:
            while True:
                cl, addr = sock.accept()
                req = cl.recv(4096).decode("utf-8")
                print("got request")
                if not req.startswith("GET /"):
                    print("invalid method")
                    PicoHttpServer.send_response(cl, "405 Method Not Allowed")
                    continue
                path = PicoHttpServer.get_path_from_request(req)
                print(f"path: {path}")
                if path not in self.methods:
                    print("path not registered")
                    PicoHttpServer.send_response(cl, "404 Not Found")
                    continue
                status, msg = self.methods[path]()
                PicoHttpServer.send_response(cl, status, msg)
        except Exception as e:
            cl.close()
            print(f"exception caught {e}")

        sock.close()

# Simple interface to control the robot
html = r"""
<html>
    <meta name="viewport" content="width=device-width, initial-scale=1.0, maximum-scale=1.0, user-scalable=0">
<body>
    <style>
        .filled {
            width: 100%;
            height: 100%;
        }
        .optgroup {
            font-size: 6vh;
            height: 33%;
            text-align: center;
        }
    </style>
    <h2 style="text-align:center">Controller</h2>
    <script>
        let interval = null;
        function buttodown(id) {
            const input = document.getElementById(id);
            input.style.background = "grey";
            fetch("/" + id);
            clearInterval(interval);
            interval = setInterval(() => {
                fetch("/" + id);
            }, 200);
        }
        function buttonup() {
            const inputs = document.getElementsByTagName("input");
            for (const input of inputs) {
                    input.style.background = "";
            }
            fetch("/stop");
            clearInterval(interval);
            interval = null;
        }
        // create control table
        const tbl = document.createElement("table");
        tbl.style.cssText = "width:70%;height:50%;margin-left:auto;margin-right:auto;";
        const labels = [null,"forward",null,null,null,null,"left_rotate","backward","right_rotate"];
        for (let rows = 0; rows < 3; rows++) {
            const tr = tbl.insertRow();
            for (let cols = 0; cols < 3; cols++) {
                const th = tr.insertCell();
                const label = labels[rows * 3 + cols];
                if (!label) {
                    continue;
                }
                const input = document.createElement("input");
                input.id = label;
                input.className = "filled";
                input.setAttribute("id", label);
                input.setAttribute("type", "button");
                input.setAttribute("value", label.toUpperCase());
                input.setAttribute("onpointerdown", "buttodown('" + label +"')");
                th.appendChild(input);
            }
        }
        document.body.appendChild(tbl);
        document.addEventListener("pointerup", buttonup);
    </script>
</body>
</html>
"""


def stop():
    movement.stop()
    return "200 OK", ""


def forward():
    movement.forward()
    return "200 OK", ""


def backward():
    movement.backward()
    return "200 OK", ""


def left_rotate():
    movement.left_rotation()
    return "200 OK", ""


def right_rotate():
    movement.right_rotation()
    return "200 OK", ""


p = PicoHttpServer()
p.register_method("/", lambda: ("200 OK", html))
p.register_method("/stop", stop)
p.register_method("/forward", forward)
p.register_method("/backward", backward)
p.register_method("/left_rotate", left_rotate)
p.register_method("/right_rotate", right_rotate)
p.run()
