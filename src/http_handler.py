import json
import signal
import threading
import uuid
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Type, TypeVar

from pydantic import BaseModel, ValidationError

from src.configuration import Configuration
from src.mailer import api_send_message
from src.structures import MailMessage, RuntimeItem
from src.utils import get_error_from_exc


T = TypeVar('T', bound=BaseModel)


class HTTPLayer(BaseHTTPRequestHandler):
    conf: Configuration

    def send_answer(
            self,
            status:
            int = 200,
            body: dict | list | str = None,
            headers: dict[str, str] = None,
            content_type: str = None
    ):
        self.send_response(status)

        if isinstance(body, dict | list):
            body = json.dumps(body, indent=4, ensure_ascii=False) + "\n"
            body = body.encode('utf-8')

            self.send_header("Content-Type", content_type or "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))

        if isinstance(body, str):
            body = body.encode('utf-8')
            self.send_header("Content-Type", content_type or "text/plain; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))

        if headers:
            [self.send_header(k, v) for k, v in headers.items()]

        self.end_headers()

        if isinstance(body, bytes):
            self.wfile.write(body)

    def validate_auth(self) -> bool:
        if not self.conf.http.auth_tokens: return True
        status = self.headers.get('Authorization') in self.conf.http.auth_tokens
        if not status:
            self.send_answer(401, 'Unauthorized')
        return status

    def validate_json_body(self, _class: Type[T]) -> T | None:
        length: int = int(self.headers.get('Content-Length'))
        body: bytes = self.rfile.read(length)
        try:
            return _class.model_validate_json(body, context={'conf': self.conf})
        except ValidationError as e:
            self.send_answer(400, get_error_from_exc(e))
            return None

    # noinspection PyPep8Naming
    def do_GET(self) -> None:
        if self.path.startswith('/message/'):
            if not self.validate_auth(): return
            guid = self.path.strip('/')[self.path.rfind('/'):]
            rtdata = self.conf.runtime.get(guid)
            if not rtdata:
                self.send_answer(404, f'Task with guid {guid} not found')
                return

            self.send_answer(
                200,
                body=rtdata.model_dump(mode='json', exclude={'content_b64'})
            )
            return

        if self.path == '/docs' and self.conf.http.docs_enabled:
            self.send_answer(200, {
                'auth_enabled': self.conf.http.auth_tokens is not None,
                'auth_header': 'Authorization',
                'auth_header_value': '<token>',
                'get': {
                    '/': {
                        'request': None,
                        'response': "text",
                    },
                    '/docs': {
                        'request': None,
                        'response': "text",
                        'title': 'Эта страница =)',
                    },
                    '/message/<guid>': {
                        'request': None,
                        'responce': RuntimeItem.model_json_schema(),
                    },
                },
                'post': {
                    '/message/send*': {
                        'request': MailMessage.model_json_schema(),
                        'response': RuntimeItem.model_json_schema(),
                    },
                },
            })


        if self.path == '/':
            self.send_answer(200, 'restmailer is serving requests')
            return

        self.send_answer(404, 'Method not found')

    # noinspection PyPep8Naming
    def do_POST(self) -> None:
        if (length := int(self.headers.get('Content-Length', 0))) > self.conf.http.max_body:
            self.send_answer(400, f'Max body is reached: {length} > {self.conf.http.max_body}')
            return

        if self.path == '/message/send' or self.path == '/message/async-send':
            if not self.validate_auth(): return

            mail_message = self.validate_json_body(MailMessage)
            if mail_message is None: return

            mail_message.guid = uuid.uuid4().hex
            self.conf.runtime[mail_message.guid] = RuntimeItem(message=mail_message)

            self.conf.runtime[mail_message.guid].log(
                'api', f'received '
                       f'data-count={len(mail_message.data)} '
                       f'text-length={sum([len(_.text) for _ in mail_message.data if _.type == 'text'])} '
                       f'target={mail_message.address_to} '
                       f'subject={mail_message.subject}'
            )

            if self.path == '/message/send':
                success_send = api_send_message(self.conf, mail_message)
                self.send_answer(
                    200 if success_send else 418,
                    body=self.conf.runtime[mail_message.guid].model_dump(mode='json', exclude={'content_b64'})
                )
                return

            threading.Thread(
                name=f'send-main-{mail_message.guid}',
                target=api_send_message,
                args=(self.conf, mail_message,),
                daemon=True
            ).start()

            self.send_answer(
                200,
                body=self.conf.runtime[mail_message.guid].model_dump(mode='json', exclude={'content_b64'})
            )
            return


        self.send_answer(404, 'Method not found')


    def log_error(self, *args, **kwargs) -> None: pass
    def log_request(self, *args, **kwargs) -> None: pass
    def log_message(self, *args, **kwargs) -> None: pass


class HTTPServer:
    conf: Configuration
    http_server: ThreadingHTTPServer | None = None
    http_instance_stop_flag: bool = False

    def __init__(self):
        self.conf = Configuration()

    def serve_http(self):
        signal.signal(signal.SIGINT, self.shutdown_instance)
        signal.signal(signal.SIGTERM, self.shutdown_instance)

        # noinspection PyTypeChecker
        self.http_server = ThreadingHTTPServer(
            (self.conf.http.listen_host, self.conf.http.listen_port),
            HTTPLayer
        )
        self.http_server.RequestHandlerClass.conf = self.conf
        print(f'HTTP server listening on {self.conf.http.listen_host}:{self.conf.http.listen_port}')

        # noinspection PyBroadException
        try:
            self.http_server.serve_forever()
        except Exception as e:
            if not self.http_instance_stop_flag: raise e
            pass

    def shutdown_instance(self, _signum=None, _=None) -> None:
        self.conf.rt_save()
        self.http_instance_stop_flag = True
        print('HTTP server shutting down')
        self.http_server.server_close()





