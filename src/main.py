import datetime

from src.http_handler import HTTPServer


if __name__ == '__main__':
    print(f'Instance starting {datetime.datetime.now().strftime('%H:%M:%S %d.%m.%y')}')
    httpserver = HTTPServer()
    httpserver.serve_http()
    print(f'Instance stopping {datetime.datetime.now().strftime('%H:%M:%S %d.%m.%y')}')
