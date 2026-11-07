"""Helpers da API de contas.

O teste do `linha()` existe por um motivo específico: o bug que ele previne
quebrava a resposta DEPOIS de a escrita já ter acontecido. O cliente via um
erro, tentava de novo, e recebia "já existe" — o pior tipo de falha, porque
o efeito colateral acontece e a confirmação não.
"""

from uuid import uuid4

import pytest
from fastapi import HTTPException

from olimpo.api.routers.accounts import (
    PRESENCE_SQL,
    SORTS,
    _assert_persona_capacity,
    _assert_persona_history_reassignable,
    _slug,
    linha,
)


class RangeFalso:
    """Imita o `int4range` como o driver o devolve — a classe se chama
    `Range` e o serializador do FastAPI não a conhece."""

    __name__ = "Range"

    def __init__(self, lower: int, upper: int) -> None:
        self.lower, self.upper = lower, upper


RangeFalso.__qualname__ = "Range"
Range = type("Range", (), {"__init__": RangeFalso.__init__})


class TestSerializacao:
    def test_converte_range_em_algo_serializavel(self):
        row = {"handle": "@x", "active_hours": Range(8, 23)}
        out = linha(row)
        assert out["active_hours"] == {"inicio": 8, "fim": 23}

    def test_preserva_o_resto_intacto(self):
        row = {"handle": "@x", "followers": 10, "labels": ["a"], "profile": {"k": "v"}}
        assert linha(row) == row

    def test_lida_com_range_nulo(self):
        assert linha({"active_hours": None})["active_hours"] is None


class TestSlug:
    def test_gera_identificador_estavel(self):
        assert _slug("Luna Prado") == "luna-prado"
        assert _slug("@luna.prado") == "luna-prado"
        assert _slug("  Chris No Beat  ") == "chris-no-beat"

    def test_nao_deixa_hifen_nas_pontas(self):
        assert _slug("!!! teste !!!") == "teste"


class TestPresenca:
    """Presença é o que a realidade diz; `status` é o que queremos. Os quatro
    estados precisam existir no SQL, senão a divergência entre intenção e
    realidade fica invisível — que é justamente o que o operador precisa ver."""

    def test_cobre_os_quatro_estados(self):
        for estado in ("unbound", "online", "stale", "missing"):
            assert f"'{estado}'" in PRESENCE_SQL

    def test_sem_placement_e_unbound_e_nao_missing(self):
        """Conta que nunca esteve num device não é conta sumida — a diferença
        importa: uma é cadastro novo, a outra é possível incidente."""
        i_unbound = PRESENCE_SQL.index("'unbound'")
        i_missing = PRESENCE_SQL.index("'missing'")
        assert i_unbound < i_missing, "unbound precisa ser avaliado antes"


class TestOrdenacao:
    def test_ordenacoes_nao_aceitam_entrada_livre(self):
        """`sort` vai direto para o ORDER BY: só valores de um mapa fechado
        podem chegar lá."""
        assert "handle" in SORTS
        assert all(";" not in v and "--" not in v for v in SORTS.values())


class ResultCount:
    def __init__(self, value: int) -> None:
        self.value = value

    def scalar(self) -> int:
        return self.value


class FakeCapacitySession:
    def __init__(self, linked_count: int) -> None:
        self.linked_count = linked_count
        self.queries: list[tuple[str, dict]] = []

    async def execute(self, query, params):
        sql = str(query)
        self.queries.append((sql, params))
        if "pg_advisory_xact_lock" in sql:
            return ResultCount(0)
        return ResultCount(self.linked_count)


@pytest.mark.asyncio
async def test_limite_persona_permita_segunda_conta() -> None:
    session = FakeCapacitySession(linked_count=1)
    await _assert_persona_capacity(session, uuid4())


@pytest.mark.asyncio
async def test_limite_persona_recusa_terceira_conta() -> None:
    session = FakeCapacitySession(linked_count=2)

    with pytest.raises(HTTPException) as erro:
        await _assert_persona_capacity(session, uuid4())

    assert erro.value.status_code == 409


@pytest.mark.asyncio
async def test_atualizacao_exclui_a_conta_que_ja_esta_vinculada() -> None:
    session = FakeCapacitySession(linked_count=1)
    await _assert_persona_capacity(session, uuid4(), excluding_account_id=uuid4())

    count_query = session.queries[1][0]
    assert "id <> :account_id" in count_query


class FakeHistorySession:
    def __init__(self, has_history: bool) -> None:
        self.has_history = has_history
        self.query = ""

    async def execute(self, query, params):
        self.query = str(query)
        return type("Result", (), {
            "first": lambda _self: ("account",) if self.has_history else None,
        })()


@pytest.mark.asyncio
async def test_troca_persona_permitida_sem_historico() -> None:
    await _assert_persona_history_reassignable(
        FakeHistorySession(False), [uuid4()], uuid4()
    )


@pytest.mark.asyncio
async def test_troca_persona_recusada_com_historico() -> None:
    session = FakeHistorySession(True)

    with pytest.raises(HTTPException) as erro:
        await _assert_persona_history_reassignable(session, [uuid4()], None)

    assert erro.value.status_code == 409
    assert all(table in session.query for table in ("story_arcs", "memories", "day_plans"))

