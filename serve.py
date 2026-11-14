"""학습 앱 서버: 이 Mac과 같은 와이파이의 휴대폰에서도 접속할 수 있게 띄운다."""
import http.server, os, socket, subprocess, sys, functools

PORT = 8765
ROOT = os.path.dirname(os.path.abspath(__file__))


def lan_ip():
    for iface in ("en0", "en1"):
        try:
            ip = subprocess.check_output(["ipconfig", "getifaddr", iface], text=True).strip()
            if ip:
                return ip
        except Exception:
            pass
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        s.connect(("10.255.255.255", 1)); return s.getsockname()[0]
    except Exception:
        return None
    finally:
        s.close()


class Handler(http.server.SimpleHTTPRequestHandler):
    def end_headers(self):
        self.send_header("Cache-Control", "no-cache")  # 수정사항이 휴대폰에 바로 반영되게
        super().end_headers()

    def log_message(self, *a):
        pass


ip = lan_ip()
url = f"http://{ip}:{PORT}" if ip else None
print("\n  English Tube 실행 중  (끄기: Ctrl+C)\n")
print(f"  이 Mac:   http://localhost:{PORT}")
if url:
    print(f"  휴대폰:   {url}   ← 같은 와이파이에서 접속\n")
    try:
        import qrcode
        q = qrcode.QRCode(border=1); q.add_data(url); q.make()
        q.print_ascii(invert=True)
        print("  휴대폰 카메라로 위 QR코드를 찍어도 열려요.\n")
    except Exception:
        pass
sys.stdout.flush()
if "--no-open" not in sys.argv:
    subprocess.Popen(["open", f"http://localhost:{PORT}"])
http.server.ThreadingHTTPServer(("0.0.0.0", PORT), functools.partial(Handler, directory=ROOT)).serve_forever()
