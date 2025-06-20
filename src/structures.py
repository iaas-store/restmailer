import base64
import email.encoders
import time
from email.mime.base import MIMEBase
from email.mime.text import MIMEText
from typing import Literal

from pydantic import BaseModel, EmailStr, Field, ConfigDict, field_validator
from pydantic_core.core_schema import ValidationInfo

from src.pydantic_list_model import ListModel


class MailMessageBodyFileItem(BaseModel):
    model_config = ConfigDict(
        title='Приложение (файл)',
    )
    type: Literal['attachment'] = 'attachment'
    name: str = Field(title='Имя файла')
    content_type: str = Field(title='Тип файла (mime-тип)')
    content_b64: str = Field(title='Содержимое файла в base64')

    @property
    def mime_object(self) -> MIMEBase:
        maintype, subtype = self.content_type.split('/', 1)
        file = MIMEBase(maintype, subtype)
        file.set_payload(base64.b64decode(self.content_b64))
        email.encoders.encode_base64(file)
        file.add_header(
            'Content-Disposition',
            'attachment',
            filename=self.name
        )
        return file


class MailMessageBodyTextItem(BaseModel):
    model_config = ConfigDict(
        title='Текстовая часть сообщения',
    )
    type: Literal['text'] = 'text'
    text: str = Field(title='Текст блока')
    subtype: Literal['plain', 'html'] | str = Field(default='plain', title='MIME-подтип')
    charset: str = Field(default='utf-8', title='Кодировка')

    @property
    def mime_object(self) -> MIMEText:
        rn_text = "\r\n".join(self.text.replace('\r\n', '\n').split("\n"))
        return MIMEText(
            rn_text,
            self.subtype,
            self.charset
        )


class MailMessage(BaseModel):
    model_config = ConfigDict(
        title='Объект отправляемого сообщения',
    )

    guid: str = Field(
        default=None,
        title='Идентификатор сообщения [read-only]',
        description='Генерируется при приеме запроса, указывать не нужно'
    )

    from_user: str | None = Field(
        default=None,
        title='Имя пользователя отправителя',
        description='Необязательно, по умолчанию берется из MAIL_DEF_USERNAME',
        validate_default=True,
    )
    from_name: str | None = Field(
        default=None,
        title='Отображаемое имя отправителя',
        description='Необязательно, по умолчанию возьмется from_user.capitalize()',
        validate_default=True,
    )

    address_to: EmailStr = Field(title='Адрес получателя')
    subject: str = Field(title='Тема сообщения')
    data: list[
        MailMessageBodyTextItem |
        MailMessageBodyFileItem
    ] = Field(default_factory=list, title='Тело сообщения и файлы')

    send_timeout: int | None = Field(
        title='Максимальное время отправки письма',
        description='По умолчанию - MAIL_DEF_MAIL_SEND_TIMEOUT - 30s',
        default=None,
        validate_default=True
    )

    ignore_starttls_cert: bool | None = Field(
        title='Игнорировать ошибки сертификата при STARTTLS upgrade',
        description='По умолчанию - MAIL_DEF_IGNORE_STARTTLS_CERT - False',
        default=None,
        validate_default=True
    )

    @field_validator('ignore_starttls_cert', mode='after')
    @staticmethod
    def using_def_ignore_starttls_cert_if_not_set(ignore_starttls_cert: bool | None, info: ValidationInfo) -> bool:
        if ignore_starttls_cert is not None: return ignore_starttls_cert

        from src.configuration import Configuration
        conf: Configuration | None = info.context['conf'] if info.context else None
        return conf.mail.def_ignore_starttls_cert if conf else False

    @field_validator('send_timeout', mode='after')
    @staticmethod
    def using_def_send_timeout_if_not_set(send_timeout: int | None, info: ValidationInfo) -> int:
        if send_timeout: return send_timeout

        from src.configuration import Configuration
        conf: Configuration | None = info.context['conf'] if info.context else None
        return conf.mail.def_mail_send_timeout if conf else 30

    @field_validator('from_user', mode='after')
    @staticmethod
    def using_def_user_if_not_set(from_user: str | None, info: ValidationInfo):
        if from_user: return from_user

        from src.configuration import Configuration
        conf: Configuration = info.context['conf']
        return conf.mail.def_username

    @field_validator('from_name', mode='after')
    @staticmethod
    def using_def_user_name_if_not_set(from_name: str | None, info: ValidationInfo):
        if from_name: return from_name

        from_user: str = info.data['from_user']
        return from_user.capitalize()


class RuntimeItemEvent(BaseModel):
    model_config = ConfigDict(
        title='Айтем лога отправки',
    )

    ts: int = Field(default_factory=lambda: int(time.time()), title='unix timestamp времени')
    source: str = Field(title='Компонент-источник сообщения')
    message: str = Field(title='Сообщение')


class RuntimeItem(BaseModel):
    model_config = ConfigDict(
        title='Информация об отправке сообщения',
    )

    message: MailMessage
    ts_added: int = Field(default_factory=lambda: int(time.time()), title='unix timestamp времени')
    state: Literal['sending', 'sended', 'error'] = 'sending'
    events: ListModel[RuntimeItemEvent] = Field(default_factory=lambda: ListModel([]), title='Лог отправки')

    def log(self, source: str, message: str):
        print(f"[{self.message.guid}] [{source}] {message}")
        self.events.append(RuntimeItemEvent(
            source=source,
            message=message
        ))
