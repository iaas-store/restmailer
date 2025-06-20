from __future__ import annotations

import hashlib
import json
import os.path
import sys
import threading
import time
from typing import Annotated

from pydantic import UrlConstraints, AnyUrl, field_validator, Field, ValidationError
from pydantic_settings import BaseSettings, SettingsConfigDict, NoDecode

from src.pydantic_dict_model import DictModel
from src.structures import RuntimeItem


class MailConfiguration(BaseSettings):
    model_config = SettingsConfigDict(
        case_sensitive=False,
        env_prefix='mail_',
        env_file=('.env.example', '.env'),
        env_file_encoding='utf-8',
        extra='ignore',
        validate_default=False
    )

    domain: str
    server_name: str
    def_username: str = 'mailserver'
    def_smtp_connect_timeout: int = 5
    def_mail_send_timeout: int = 30
    def_ignore_starttls_cert: bool = False
    proxy: Annotated[AnyUrl, UrlConstraints(allowed_schemes=['http', 'socks4', 'socks5'])] | None = None
    dkim_key_path: str | None = None
    dkim_selector: str = 'mail'

    @field_validator('dkim_key_path', mode='after')
    @staticmethod
    def check_dkim_file(dkim_key_path: str):
        assert os.path.isfile(dkim_key_path), 'dkim_key path is incorrect'

        from src.mailer import dkim_sign
        from email.mime.multipart import MIMEMultipart

        msg = MIMEMultipart()
        msg['From'] = 'example@example.com'

        sign = dkim_sign(dkim_key_path, 'mail', 'example.com', msg)
        assert sign is not None, 'dkim_key has incorrect format'

        return dkim_key_path


class HttpConfiguration(BaseSettings):
    model_config = SettingsConfigDict(
        case_sensitive=False,
        env_prefix='http_',
        env_file=('.env.example', '.env'),
        env_file_encoding='utf-8',
        extra='ignore',
    )

    listen_host: str = '0.0.0.0'
    listen_port: int = 80
    max_body: int = Field(default=20_971_520, ge=1_024, le=52_428_800)
    runtime_file_path: str | None = Field(validate_default=False, default=None)
    auth_tokens: Annotated[list[str], NoDecode] | None = None
    docs_enabled: bool = False

    @field_validator('runtime_file_path', mode='after')
    @staticmethod
    def check_runtime_file_path_is_writable(runtime_file_path: str):
        exists = os.path.isfile(runtime_file_path)
        if exists:
            assert os.access(runtime_file_path, os.W_OK), 'runtime_file is not writable'
            RuntimeHolder.load(runtime_file_path)

        return runtime_file_path

    @field_validator('auth_tokens', mode='before')
    @staticmethod
    def convert_auth_tokens(v: str | None) -> list[str] | None:
        if not v: return None
        return [x.strip(' ') for x in v.split(',')]

    @field_validator('auth_tokens', mode='after')
    @staticmethod
    def warning_if_auth_tokens_is_none(auth_tokens: list[str] | None):
        if auth_tokens is None:
            print('[startup] auth_tokens is None, API working in not secure mode', file=sys.stderr)
        return auth_tokens


class RuntimeHolder(DictModel[str, RuntimeItem]):
    @classmethod
    def load(cls, runtime_file_path: str | None):
        if runtime_file_path and os.path.isfile(runtime_file_path):
            content: bytes = open(runtime_file_path, 'rb').read()
            content: dict = json.loads(content) if content else {}
        else:
            content: dict = {}
        return cls.model_validate(content)

    def dump(self, runtime_file_path: str | None):
        if not runtime_file_path: return
        with open(runtime_file_path, 'w', encoding='utf-8') as f:
            f.write(self.model_dump_json(indent=2))


class Configuration:
    mail: MailConfiguration
    http: HttpConfiguration
    runtime: RuntimeHolder

    def rt_save(self):
        if self.http.runtime_file_path:
            with open(self.http.runtime_file_path, 'w', encoding='utf-8') as f:
                f.write(self.runtime.model_dump_json(indent=2))

    def _cleanup_runtime(self):
        last_rt_hash = None

        while True:
            rt = json.dumps({k: v.model_dump(mode='json') for k, v in self.runtime.items()})
            rt_hash = hashlib.sha256(rt.encode()).digest().hex()
            data_len = len(rt)
            if data_len > 50 * 1024**3:
                self.runtime.pop(list(self.runtime.keys())[0])

            if last_rt_hash != rt_hash:
                self.rt_save()
            last_rt_hash = rt_hash
            time.sleep(10)

    # noinspection PyArgumentList
    def __init__(self):
        self.http = HttpConfiguration()
        self.mail = MailConfiguration()
        self.runtime = RuntimeHolder.load(self.http.runtime_file_path)

        threading.Thread(
            name='runtime-cleanup',
            target=self._cleanup_runtime,
            daemon=True
        ).start()

    def __str__(self):
        return json.dumps({
            'mail': self.mail.model_dump(mode='json'),
            'http': self.http.model_dump(mode='json'),
            'runtime': self.runtime.model_dump(mode='json')
        }, indent=2, ensure_ascii=True)

