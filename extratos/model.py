from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from decimal import Decimal


@dataclass
class Lancamento:
    fonte: str          # bb | itau | santander | rede
    conta: str
    data: date
    descricao: str
    valor: Decimal      # positivo = crédito, negativo = débito
    documento: str = ""
    arquivo: str = ""

    @property
    def chave(self) -> tuple:
        return (self.fonte, self.conta, self.data, self.valor, self.documento, self.descricao)


@dataclass
class Titulo:
    nosso_numero: str
    documento: str
    sacado: str
    vencimento: date | None
    valor: Decimal
    status: str = "aberto"   # aberto | liquidado | baixado | rejeitado
    valor_pago: Decimal = Decimal("0")
    data_credito: date | None = None
    arquivo: str = ""

    def situacao(self, ref: date) -> str:
        if self.status != "aberto":
            return self.status
        if self.vencimento and self.vencimento < ref:
            return "vencido"
        return "a vencer"
