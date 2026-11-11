import re
from datetime import date
from typing import Literal
from pydantic import BaseModel, ConfigDict, Field, field_validator

Stage = Literal['novos', 'negociando', 'followup', 'aguardando', 'vendidos', 'perdidos']
Origin = Literal['WhatsApp', 'Instagram', 'Indicação', 'Outros']


def normalize_phone(value: str) -> str:
    """International digits. Assume Brazil only for 10/11-digit local input.

    Do not insert/remove Brazil's ninth digit: that can merge distinct numbers.
    """
    value = value.strip()
    if not value:
        return ''
    if re.search(r'[^\d\s()+.\-]', value):
        raise ValueError('Telefone inválido; informe DDI, DDD e número.')
    digits = re.sub(r'\D', '', value)
    if digits.startswith('00'):
        digits = digits[2:]
    elif not value.startswith('+') and len(digits) in (10, 11):
        digits = '55' + digits
    if not 8 <= len(digits) <= 15 or digits[0] == '0':
        raise ValueError('Telefone inválido; informe DDI, DDD e número.')
    return digits


class ClientFields(BaseModel):
    model_config = ConfigDict(extra='forbid', str_max_length=5000)
    name: str = Field(min_length=1, max_length=200)
    phone: str = Field(default='', max_length=40)
    wa: str = Field(default='', max_length=40)
    ig: str = Field(default='', max_length=255)
    origin: Origin = 'WhatsApp'
    product: str = Field(default='', max_length=200)
    model: str = Field(default='', max_length=200)
    storage: str = Field(default='', max_length=100)
    color: str = Field(default='', max_length=100)
    budget: float = Field(default=0, ge=0, le=1e12, allow_inf_nan=False)
    value: float = Field(default=0, ge=0, le=1e12, allow_inf_nan=False)
    notes: str = ''
    created: date = Field(default_factory=date.today)

    @field_validator('name')
    @classmethod
    def name_not_blank(cls, value):
        if not value.strip():
            raise ValueError('Informe o nome.')
        return value.strip()

    @field_validator('phone', 'wa')
    @classmethod
    def phone_valid(cls, value):
        normalize_phone(value)
        return value


class EditClient(BaseModel):
    version: int = Field(ge=1)
    fields: ClientFields


class Action(BaseModel):
    model_config = ConfigDict(extra='forbid')
    version: int = Field(ge=1)
    kind: Literal['stage', 'follow_done', 'follow_reply', 'follow_date', 'reason']
    stage: Stage | None = None
    value: float = Field(default=0, ge=0, le=1e12, allow_inf_nan=False)
    reason: str = Field(default='', max_length=200)
    follow: date | None = None


class ConfigFields(BaseModel):
    model_config = ConfigDict(extra='forbid')
    loja: str = Field(default='Minha loja', max_length=200)
    admin: str = Field(default='Administrador', max_length=200)
    telefone: str = Field(default='11977321570', max_length=40)
    dias: int = Field(default=2, ge=1, le=365)
    n1: bool = True
    n2: bool = True
    n3: bool = False

    @field_validator('telefone')
    @classmethod
    def phone_valid(cls, value):
        normalize_phone(value)
        return value


class EditConfig(BaseModel):
    version: int = Field(ge=1)
    fields: ConfigFields


class Login(BaseModel):
    username: str = Field(max_length=200)
    password: str = Field(max_length=1024)
