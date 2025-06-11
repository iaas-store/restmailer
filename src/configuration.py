import hashlib
import json
import os.path
import sys
import threading
import time
from typing import Annotated

from pydantic import UrlConstraints, AnyUrl, field_validator, Field
from pydantic_settings import BaseSettings, SettingsConfigDict, NoDecode

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
    def_timeout: int = 5
    proxy: Annotated[AnyUrl, UrlConstraints(allowed_schemes=['http', 'socks4', 'socks5'])] | None = None
    dkim_key_path: str | None = None

    @field_validator('dkim_key_path', mode='after')
    @staticmethod
    def check_dkim_file_present(dkim_key_path: str):
        assert os.path.isfile(dkim_key_path), 'dkim_key path is incorrect'
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
            content: str = open(runtime_file_path, 'r', encoding='utf-8').read()
            content: dict = json.loads(content) if content else {}
            for k, v in content.items():
                RuntimeItem.model_validate(v)
        else:
            f = open(runtime_file_path, 'w')
            f.write('{}')
            f.flush()
            f.close()

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

class Configuration:
    mail: MailConfiguration
    http: HttpConfiguration
    runtime: dict[str, RuntimeItem]

    def rt_save(self):
        if self.http.runtime_file_path:
            with open(self.http.runtime_file_path, 'w', encoding='utf-8') as f:
                f.write(json.dumps(
                    {k: v.model_dump(mode='json') for k, v in self.runtime.items()},
                    indent=2, ensure_ascii=False
                ))

    def _cleanup_runtime(self):
        last_rt_hash = None

        while True:
            rt = json.dumps({k: v.model_dump(mode='json') for k, v in self.runtime.items()})
            rt_hash = hashlib.sha256(rt.encode()).digest().hex()
            data_len = len(rt)
            if data_len > 100 * 1024**3:
                self.runtime.pop(list(self.runtime.keys())[0])

            if last_rt_hash != rt_hash:
                self.rt_save()
            last_rt_hash = rt_hash
            time.sleep(10)

    # noinspection PyArgumentList
    def __init__(self):
        self.http = HttpConfiguration()
        self.mail = MailConfiguration()
        self.runtime = {}

        threading.Thread(
            name='runtime-cleanup',
            target=self._cleanup_runtime,
            daemon=True
        ).start()

    def __str__(self):
        return json.dumps({
            'mail': self.mail.model_dump(mode='json'),
            'http': self.http.model_dump(mode='json'),
            'runtime': {k: v.model_dump(mode='json') for k, v in self.runtime.items()}
        }, indent=2, ensure_ascii=True)

