import http.server
import socketserver

PORT = 80

class Handler(http.server.SimpleHTTPRequestHandler):
    def address_string(self):
        return str(self.client_address[0])

    def log_message(self, format, *args):
        pass

httpd = socketserver.TCPServer(("", PORT), Handler)
print("Server1: httpd serving at port", PORT)
httpd.serve_forever()
