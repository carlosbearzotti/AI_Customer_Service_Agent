"""Testes do loop com LLM simulado: não avaliam a qualidade das respostas do modelo."""
import json
import threading
from datetime import datetime
from http.server import BaseHTTPRequestHandler, HTTPServer

import pytest

from emporio import cli, exemplos, tools
from emporio.agent import MAX_ITERACOES, RESPOSTA_LIMITE, Agente, ClienteOpenAICompativel, ErroLLM
from emporio.ingest import ingerir


class Roteiro:
    def __init__(self, *respostas):
        self.respostas = list(respostas)
        self.recebido = []

    def completar(self, mensagens, schemas):
        self.recebido.append(list(mensagens))
        r = self.respostas.pop(0)
        if isinstance(r, Exception):
            raise r
        return r


def tool_call(nome, args, id_="c1"):
    arguments = args if isinstance(args, str) else json.dumps(args)
    return {"content": None, "tool_calls": [{"id": id_, "type": "function",
                                             "function": {"name": nome, "arguments": arguments}}]}


@pytest.fixture
def con(tmp_path):
    path = tmp_path / "t.db"
    ingerir(path)
    c = tools.conectar(path)
    yield c
    c.close()


def test_resultado_da_tool_volta_ao_modelo(con):
    llm = Roteiro(tool_call("consultar_preco", {"produto_id": 95}), {"content": "R$ 2.199"})
    agente = Agente(llm, con)
    assert agente.responder("Preço do Takamine?") == "R$ 2.199"
    msg_tool = llm.recebido[1][-1]
    assert msg_tool["role"] == "tool" and msg_tool["tool_call_id"] == "c1"
    assert json.loads(msg_tool["content"])["preco_pix"] == 2089.05
    assert agente.chamadas[0]["tool"] == "consultar_preco"


def test_historico_passa_entre_turnos(con):
    llm = Roteiro({"content": "Oi"}, {"content": "Claro"})
    agente = Agente(llm, con)
    agente.responder("primeira")
    agente.responder("segunda")
    assert [m["content"] for m in llm.recebido[1] if m["role"] == "user"] == ["primeira", "segunda"]
    assert llm.recebido[1][0]["role"] == "system"


def test_argumentos_invalidos_viram_erro_para_o_modelo(con):
    llm = Roteiro(tool_call("consultar_preco", "{nao json"), {"content": "ok"})
    assert Agente(llm, con).responder("x") == "ok"
    assert json.loads(llm.recebido[1][-1]["content"]) == {"erro": "argumentos_invalidos"}


def test_argumentos_ja_em_dict_sao_aceitos(con):
    chamada = tool_call("consultar_preco", {})
    chamada["tool_calls"][0]["function"]["arguments"] = {"produto_id": 95}
    llm = Roteiro(chamada, {"content": "ok"})
    Agente(llm, con).responder("x")
    assert json.loads(llm.recebido[1][-1]["content"])["produto_id"] == 95


def test_reasoning_content_volta_ao_modelo(con):
    chamada = {**tool_call("verificar_expediente", {}), "reasoning_content": "pensei"}
    llm = Roteiro(chamada, {"content": "fim", "reasoning_content": "concluí"}, {"content": "ok"})
    agente = Agente(llm, con)
    agente.responder("x")
    assert llm.recebido[1][2]["reasoning_content"] == "pensei"
    agente.responder("y")
    assert [m.get("reasoning_content") for m in llm.recebido[2] if m["role"] == "assistant"] == ["pensei", "concluí"]


@pytest.mark.parametrize("agora,trecho", [
    (datetime(2026, 3, 25, 10, 0), "em horário de atendimento"),
    (datetime(2026, 3, 29, 10, 0), "retorna em segunda-feira às 09:00"),
])
def test_expediente_vai_no_prompt_sem_depender_do_modelo(con, agora, trecho):
    agente = Agente(Roteiro({"content": "oi"}), con, relogio=lambda: agora)
    agente.responder("x")
    assert trecho in agente.historico[0]["content"]
    assert str(agora.year) not in agente.historico[0]["content"].split("CONTEXTO ATUAL")[1]


def test_aviso_de_fechado_so_no_primeiro_turno(con):
    domingo = datetime(2026, 3, 29, 10, 0)
    agente = Agente(Roteiro({"content": "oi"}, {"content": "ok"}), con, relogio=lambda: domingo)
    agente.responder("a")
    assert "nesta primeira resposta" in agente.historico[0]["content"]
    agente.responder("b")
    assert "Não repita o aviso" in agente.historico[0]["content"]


def test_loop_tem_limite(con):
    llm = Roteiro(*[tool_call("verificar_expediente", {}) for _ in range(MAX_ITERACOES)])
    assert Agente(llm, con).responder("x") == RESPOSTA_LIMITE


def test_falha_do_llm_desfaz_o_turno(con):
    llm = Roteiro(tool_call("verificar_expediente", {}), ErroLLM("caiu"), {"content": "voltei"})
    agente = Agente(llm, con)
    with pytest.raises(ErroLLM):
        agente.responder("x")
    assert len(agente.historico) == 1
    assert agente.responder("y") == "voltei"


def test_cli_sobrevive_a_erro_e_encerra(con):
    agente = Agente(Roteiro(ErroLLM("caiu"), {"content": "resposta"}), con)
    entradas, saidas = iter(["a", "", "\ufffc", "▾ -", "b", "sair"]), []
    cli.conversar(agente, entrada=lambda _: next(entradas), saida=saidas.append)
    assert any("[erro]" in s for s in saidas) and "tom> resposta" in saidas


def test_gerador_de_exemplos_registra_tools(con, tmp_path):
    llm = Roteiro(tool_call("consultar_preco", {"produto_id": 95}), {"content": "R$ 2.199"})
    texto = exemplos.gerar("t", ["Preço?"], Agente(llm, con), tmp_path).read_text(encoding="utf-8")
    assert "**Cliente:** Preço?" in texto and "consultar_preco" in texto and "**Tom:** R$ 2.199" in texto


@pytest.fixture
def servidor():
    recebido = {}

    class Handler(BaseHTTPRequestHandler):
        def do_POST(self):
            recebido["path"] = self.path
            recebido["auth"] = self.headers["Authorization"]
            recebido["corpo"] = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
            dados = json.dumps({"choices": [{"message": {"content": "oi"}}]}).encode()
            self.send_response(200)
            self.end_headers()
            self.wfile.write(dados)

        def log_message(self, *a):
            pass

    srv = HTTPServer(("127.0.0.1", 0), Handler)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    yield f"http://127.0.0.1:{srv.server_port}/v1", recebido
    srv.shutdown()


def test_cliente_http_envia_formato_compativel(servidor):
    url, recebido = servidor
    r = ClienteOpenAICompativel(url, "m", "k").completar([{"role": "user", "content": "x"}], tools.SCHEMAS)
    assert r["content"] == "oi" and recebido["path"] == "/v1/chat/completions"
    assert recebido["auth"] == "Bearer k" and recebido["corpo"]["model"] == "m"
    assert recebido["corpo"]["tools"][0]["type"] == "function"


def test_cliente_http_envia_parametros_extras(servidor):
    url, recebido = servidor
    ClienteOpenAICompativel(url, "m", "k", '{"thinking": {"type": "disabled"}}').completar([], [])
    assert recebido["corpo"]["thinking"] == {"type": "disabled"}


def test_cliente_sem_chave_explica_o_problema(monkeypatch):
    monkeypatch.delenv("LLM_API_KEY", raising=False)
    with pytest.raises(ErroLLM, match="LLM_API_KEY"):
        ClienteOpenAICompativel("http://127.0.0.1:9/v1", "m").completar([], [])


def test_cliente_http_sem_servidor_vira_erro_llm():
    with pytest.raises(ErroLLM):
        ClienteOpenAICompativel("http://127.0.0.1:9/v1", "m", "k").completar([], [])
