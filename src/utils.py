from urllib.parse import urlencode

import requests
from pydantic import ValidationError
from pydantic_core import ErrorDetails


def get_mx_server_address(domain: str) -> list[str]:
    # noinspection PyBroadException
    try:
        address = []
        args = {
            'name': domain,
            'type': 'MX',
            'ct': 'application/x-javascript',
            'edns_client_subnet': '0.0.0.0/0',
            'cd': 'false',
        }
        res: dict = requests.get(f'https://dns.google/resolve?{urlencode(args)}').json()
        # https://developers.google.com/speed/public-dns/docs/doh/json

        if res['Status'] == 0:
            datas = [answer['data'].strip('.') for answer in res['Answer'] if answer['type'] == 15]
            datas = sorted(datas, key=lambda x: int(x.split(' ')[0]))
            datas = [_.split(' ')[1] if ' ' in _ else _ for _ in datas]
            return datas

    except Exception:
        address = []

    return address


def get_error_from_exc(exc: ValidationError):
    errors: list[ErrorDetails] = exc.errors()
    return {
        'error': ', '.join([decode_pydantic_error(_) for _ in errors]),
        'fields': ['.'.join([str(l) for l in error['loc']]) for error in errors]
    }


def decode_pydantic_error(error: ErrorDetails) -> (str, str):
    loc = '.'.join([str(l) for l in error['loc']])
    msg = str(error['msg']).replace('Assertion failed, ', '')
    return f'{loc}: {msg}' if loc else msg
