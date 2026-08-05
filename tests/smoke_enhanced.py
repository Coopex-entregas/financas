from datetime import date, timedelta

import enhanced_app as enhanced

app = enhanced.app
db = enhanced.db
Usuario = enhanced.Usuario
Cooperado = enhanced.Cooperado
Restaurante = enhanced.Restaurante
Escala = enhanced.Escala
Lancamento = enhanced.Lancamento
ProducaoPendente = enhanced.ProducaoPendente


def set_session(client, user_id: int, role: str) -> None:
    with client.session_transaction() as sess:
        sess["user_id"] = user_id
        sess["user_tipo"] = role


def main() -> None:
    with app.app_context():
        db.drop_all()
        db.create_all()

        coop_user = Usuario(usuario="coop_teste", senha_hash="", tipo="cooperado", ativo=True)
        coop_user.set_password("teste123")
        rest_user = Usuario(usuario="rest_teste", senha_hash="", tipo="restaurante", ativo=True)
        rest_user.set_password("teste123")
        admin_user = Usuario(usuario="admin_teste", senha_hash="", tipo="admin", ativo=True)
        admin_user.set_password("teste123")
        db.session.add_all([coop_user, rest_user, admin_user])
        db.session.flush()

        coop = Cooperado(nome="Cooperado Teste", usuario_id=coop_user.id)
        rest = Restaurante(nome="Contrato Teste", periodo="seg-dom", usuario_id=rest_user.id)
        db.session.add_all([coop, rest])
        db.session.flush()

        worked_date = date.today() - timedelta(days=1)
        scale = Escala(
            cooperado_id=coop.id,
            restaurante_id=rest.id,
            data=worked_date.strftime("%d/%m/%Y"),
            turno="Dia",
            horario="08:00 - 10:00",
            contrato=rest.nome,
        )
        db.session.add(scale)
        db.session.commit()

        coop_user_id = coop_user.id
        rest_user_id = rest_user.id
        admin_user_id = admin_user.id
        coop_id = coop.id
        rest_id = rest.id
        scale_id = scale.id
        date_text = worked_date.strftime("%Y-%m-%d")

    client = app.test_client()
    set_session(client, coop_user_id, "cooperado")

    response = client.post(
        "/coop/producoes/nova",
        data={
            "escala_id": scale_id,
            "qtd_entregas": 10,
            "valor": "100.00",
            "descricao": "Teste funcional",
        },
        follow_redirects=False,
    )
    assert response.status_code == 302
    assert "/coop/producoes/" in response.headers["Location"]

    with app.app_context():
        assert ProducaoPendente.query.count() == 1
        pending_id = ProducaoPendente.query.one().id

    # Enviar novamente o mesmo turno não duplica.
    response = client.post(
        "/coop/producoes/nova",
        data={"escala_id": scale_id, "qtd_entregas": 10, "valor": "100.00"},
        follow_redirects=False,
    )
    assert response.status_code == 302
    with app.app_context():
        assert ProducaoPendente.query.count() == 1
        assert Lancamento.query.count() == 0

    # Avaliação opcional do contrato antes da aprovação.
    response = client.post(
        f"/coop/producoes/{pending_id}/avaliar",
        data={"ambiente": 5, "tratamento": 4, "suporte": 5, "comentario": "Bom contrato"},
        follow_redirects=False,
    )
    assert response.status_code == 302

    set_session(client, rest_user_id, "restaurante")
    status = client.get("/api/rest/producoes/pendentes/status").get_json()
    assert status["ok"] is True and status["count"] == 1

    # O estabelecimento corrige quantidade/valor e aprova.
    response = client.post(
        f"/rest/producoes/{pending_id}/aprovar",
        data={"qtd_entregas": 11, "valor": "105.00"},
        follow_redirects=False,
    )
    assert response.status_code == 302

    with app.app_context():
        pending = db.session.get(ProducaoPendente, pending_id)
        assert pending.status == "aprovada"
        assert pending.valor_aprovado == 105.0
        launch = Lancamento.query.one()
        assert launch.restaurante_id == rest_id
        assert launch.cooperado_id == coop_id
        assert launch.qtd_entregas == 11
        assert launch.valor == 105.0
        launch_id = launch.id

    # O formulário legado do estabelecimento encontra o turno existente e não cria outro.
    response = client.post(
        "/restaurante/lancar_producao",
        data={
            "cooperado_id": coop_id,
            "qtd_entregas": 11,
            "valor": "105.00",
            "data": date_text,
            "hora_inicio": "08:00",
            "hora_fim": "10:00",
        },
        follow_redirects=False,
    )
    assert response.status_code == 302
    with app.app_context():
        assert Lancamento.query.count() == 1
        assert Lancamento.query.one().id == launch_id
        assert enhanced._find_existing_slot(rest_id, coop_id, date.today() - timedelta(days=1), "09:00", "09:30") is not None

    # Edição rápida do admin e exclusão via API continuam funcionais.
    set_session(client, admin_user_id, "admin")
    response = client.patch(
        f"/api/admin/lancamentos/{launch_id}",
        json={
            "restaurante_id": rest_id,
            "cooperado_id": coop_id,
            "data": date_text,
            "hora_inicio": "08:00",
            "hora_fim": "10:00",
            "qtd_entregas": 12,
            "valor": 110.0,
            "descricao": "Ajustado no admin rápido",
        },
    )
    assert response.status_code == 200 and response.get_json()["ok"] is True
    with app.app_context():
        launch = db.session.get(Lancamento, launch_id)
        assert launch.qtd_entregas == 12 and launch.valor == 110.0

    response = client.delete(f"/api/admin/lancamentos/{launch_id}")
    assert response.status_code == 200 and response.get_json()["ok"] is True
    with app.app_context():
        assert Lancamento.query.count() == 0
        pending = db.session.get(ProducaoPendente, pending_id)
        assert pending.lancamento_id is None

    print("functional production workflow validated")


if __name__ == "__main__":
    main()
