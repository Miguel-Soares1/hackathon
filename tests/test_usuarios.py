"""Login por usuário e senha, sessões e administração de usuários (ADR-018)."""
import pytest

from conftest import CHAVE
from triagem import usuarios


def admin(client, usuario="ana", senha="senha-forte-1"):
    """Cria o 1º administrador pela tela inicial e devolve o header da sessão."""
    r = client.post("/auth/primeiro-admin", json={"chave_api": "chave-de-teste", "usuario": usuario,
                                                  "nome": "Ana Admin", "senha": senha})
    assert r.status_code == 201, r.text
    return {"Authorization": f"Bearer {r.json()['token']}"}


def entrar(client, usuario, senha, manter=True):
    return client.post("/auth/login", json={"usuario": usuario, "senha": senha, "manter_conectado": manter})


# ---------- senha ----------
def test_senha_fica_so_como_hash_com_sal():
    h1, h2 = usuarios.gerar_hash("minha-senha"), usuarios.gerar_hash("minha-senha")
    assert h1 != h2 and "minha-senha" not in h1 and h1.startswith("pbkdf2_sha256$")
    assert usuarios.senha_confere("minha-senha", h1) and not usuarios.senha_confere("outra-senha", h1)
    assert not usuarios.senha_confere("x", "lixo")


# ---------- primeiro acesso ----------
def test_primeiro_admin_exige_a_chave_do_servidor_e_so_funciona_uma_vez(client):
    assert client.get("/auth/estado").json() == {"precisa_configurar": True}
    errada = client.post("/auth/primeiro-admin", json={"chave_api": "errada", "usuario": "ana", "nome": "A", "senha": "senha-forte-1"})
    assert errada.status_code == 401
    admin(client)
    assert client.get("/auth/estado").json() == {"precisa_configurar": False}
    de_novo = client.post("/auth/primeiro-admin", json={"chave_api": "chave-de-teste", "usuario": "bob", "nome": "B", "senha": "senha-forte-2"})
    assert de_novo.status_code == 409


# ---------- login e sessão ----------
def test_login_abre_sessao_que_acessa_o_painel(client):
    admin(client)
    r = entrar(client, "ANA", "senha-forte-1")  # usuário sem diferenciar maiúsculas
    assert r.status_code == 200
    sessao = {"Authorization": f"Bearer {r.json()['token']}"}
    assert r.json()["usuario"]["papel"] == "admin" and "senha_hash" not in r.json()["usuario"]
    assert client.get("/tickets", headers=sessao).status_code == 200
    assert client.get("/auth/eu", headers=sessao).json()["usuario"] == "ana"


@pytest.mark.parametrize("usuario, senha", [("ana", "errada-123"), ("nao-existe", "senha-forte-1")])
def test_login_errado_nao_diz_o_que_errou(client, usuario, senha):
    admin(client)
    r = entrar(client, usuario, senha)
    assert r.status_code == 401 and r.json()["detail"] == "usuário ou senha incorretos"


def test_logout_e_token_invalido_perdem_o_acesso(client):
    sessao = admin(client)
    assert client.post("/auth/logout", headers=sessao).status_code == 204
    assert client.get("/tickets", headers=sessao).status_code == 401
    assert client.get("/tickets", headers={"Authorization": "Bearer inventado"}).status_code == 401


def test_chave_de_api_continua_valendo_para_integracoes_mas_nao_para_administrar(client):
    admin(client)
    assert client.get("/tickets", headers=CHAVE).status_code == 200
    assert client.get("/usuarios", headers=CHAVE).status_code == 401


def test_resposta_no_chat_sai_com_o_nome_de_quem_esta_logado(client):
    sessao = admin(client)
    r = client.post("/webhook/mensagens", headers=CHAVE, json={"canal": "chat", "texto": "meu pix não caiu"})
    tid = r.json()["ticket_id"]
    client.post(f"/tickets/{tid}/mensagens", headers=sessao, json={"texto": "Já vou ver!", "autor": "Outra Pessoa"})
    assert client.get(f"/tickets/{tid}/mensagens", headers=sessao).json()[-1]["autor"] == "Ana Admin"


def test_muitas_tentativas_de_login_sao_bloqueadas(client):
    admin(client)
    codigos = [entrar(client, "ana", f"errada-{n}").status_code for n in range(12)]
    assert 429 in codigos


# ---------- administração ----------
def test_admin_cria_atendente_que_entra_mas_nao_administra(client):
    sessao = admin(client)
    r = client.post("/usuarios", headers=sessao, json={"usuario": "joao", "nome": "João", "senha": "senha-joao-1"})
    assert r.status_code == 201 and r.json()["papel"] == "atendente"
    joao = {"Authorization": f"Bearer {entrar(client, 'joao', 'senha-joao-1').json()['token']}"}
    assert client.get("/tickets", headers=joao).status_code == 200
    assert client.get("/usuarios", headers=joao).status_code == 403
    assert client.post("/usuarios", headers=sessao, json={"usuario": "joao", "nome": "J", "senha": "senha-joao-2"}).status_code == 409
    assert client.post("/usuarios", headers=sessao, json={"usuario": "maria", "nome": "M", "senha": "curta"}).status_code == 400


def test_admin_redefine_senha_e_desativa_derrubando_as_sessoes(client):
    sessao = admin(client)
    uid = client.post("/usuarios", headers=sessao, json={"usuario": "joao", "nome": "João", "senha": "senha-joao-1"}).json()["id"]
    joao = {"Authorization": f"Bearer {entrar(client, 'joao', 'senha-joao-1').json()['token']}"}
    # redefinir a senha derruba a sessão aberta e a senha antiga para de valer
    assert client.patch(f"/usuarios/{uid}", headers=sessao, json={"senha": "nova-senha-joao"}).status_code == 200
    assert client.get("/tickets", headers=joao).status_code == 401
    assert entrar(client, "joao", "senha-joao-1").status_code == 401
    assert entrar(client, "joao", "nova-senha-joao").status_code == 200
    # desativado não entra mais
    assert client.patch(f"/usuarios/{uid}", headers=sessao, json={"ativo": False}).json()["ativo"] is False
    assert entrar(client, "joao", "nova-senha-joao").status_code == 401


def test_sistema_nunca_fica_sem_administrador(client):
    sessao = admin(client)
    eu = client.get("/auth/eu", headers=sessao).json()["id"]
    r = client.patch(f"/usuarios/{eu}", headers=sessao, json={"papel": "atendente"})
    assert r.status_code == 400 and "administrador" in r.json()["detail"]
    assert client.patch(f"/usuarios/{eu}", headers=sessao, json={"ativo": False}).status_code == 400


def test_usuario_troca_a_propria_senha(client):
    sessao = admin(client)
    errada = client.post("/auth/senha", headers=sessao, json={"senha_atual": "errada-123", "nova_senha": "nova-senha-ana"})
    assert errada.status_code == 400
    assert client.post("/auth/senha", headers=sessao, json={"senha_atual": "senha-forte-1", "nova_senha": "nova-senha-ana"}).status_code == 204
    assert client.get("/tickets", headers=sessao).status_code == 200  # a sessão atual continua
    assert entrar(client, "ana", "nova-senha-ana").status_code == 200
