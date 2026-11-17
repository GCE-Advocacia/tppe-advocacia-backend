import pytest

THEMES_URL = "/api/v1/office-config/themes"
OFFICE_CONFIG_URL = "/api/v1/office-config"


def valid_theme_payload(name="Tema Customizado Teste"):
    return {
        "name": name,
        "description": "Uma bela descrição",
        "color": "#112233",
        "color_bg_primary": "#112233",
        "color_bg_secondary": "#f4f4f4",
        "color_bg_sobre": "#ffffff",
        "color_buttons": "#c5a059",
        "color_buttons_hover": "#a38038",
        "color_buttons_text": "#ffffff",
        "color_title_primary": "#ffffff",
        "color_title_secondary": "#112233",
        "color_text_primary": "#ffffff",
        "color_text_secondary": "#555555",
        "color_link_primary": "#ffffff",
        "color_link_secondary": "#c5a059",
    }


class TestListThemesE2E:
    def test_returns_at_least_3_predefined_themes(self, client):
        response = client.get(THEMES_URL)
        assert response.status_code == 200
        data = response.json()["data"]
        assert len(data) >= 3
        predefined = [t for t in data if t["is_predefined"]]
        assert len(predefined) >= 3
        assert any(t["name"] == "Clássico Navy & Wine (Padrão)" for t in predefined)


class TestCreateThemeE2E:
    def test_non_admin_cannot_create_theme(self, client, user_headers):
        response = client.post(
            THEMES_URL,
            json=valid_theme_payload(),
            headers=user_headers,
        )
        assert response.status_code == 403

    def test_admin_can_create_theme(self, client, admin_headers):
        payload = valid_theme_payload("Tema Admin E2E")
        response = client.post(
            THEMES_URL,
            json=payload,
            headers=admin_headers,
        )
        assert response.status_code == 201
        data = response.json()["data"]
        assert data["name"] == "Tema Admin E2E"
        assert data["is_predefined"] is False
        assert data["color"] == "#112233"

        # Cleanup
        theme_id = data["id"]
        client.delete(f"{THEMES_URL}/{theme_id}", headers=admin_headers)


class TestUpdateAndDeleteThemeE2E:
    def test_admin_can_update_theme(self, client, admin_headers):
        # Create theme first
        res = client.post(
            THEMES_URL,
            json=valid_theme_payload("Tema Para Atualizar"),
            headers=admin_headers,
        )
        theme_id = res.json()["data"]["id"]

        update_res = client.put(
            f"{THEMES_URL}/{theme_id}",
            json={"name": "Tema Atualizado com Sucesso", "color_buttons": "#990000"},
            headers=admin_headers,
        )
        assert update_res.status_code == 200
        data = update_res.json()["data"]
        assert data["name"] == "Tema Atualizado com Sucesso"
        assert data["color_buttons"] == "#990000"

        # Cleanup
        client.delete(f"{THEMES_URL}/{theme_id}", headers=admin_headers)

    def test_admin_cannot_delete_predefined_theme(self, client, admin_headers):
        res = client.get(THEMES_URL)
        themes = res.json()["data"]
        predef = next(t for t in themes if t["is_predefined"])

        del_res = client.delete(
            f"{THEMES_URL}/{predef['id']}",
            headers=admin_headers,
        )
        assert del_res.status_code == 403
        assert del_res.json()["error"]["code"] == "PREDEFINED_THEME_DELETE_NOT_ALLOWED"

    def test_admin_can_delete_custom_theme(self, client, admin_headers):
        res = client.post(
            THEMES_URL,
            json=valid_theme_payload("Tema Para Deletar"),
            headers=admin_headers,
        )
        theme_id = res.json()["data"]["id"]

        del_res = client.delete(f"{THEMES_URL}/{theme_id}", headers=admin_headers)
        assert del_res.status_code == 204

        # Verify it no longer exists
        get_res = client.get(THEMES_URL)
        assert all(t["id"] != theme_id for t in get_res.json()["data"])


class TestThemeQuotaE2E:
    def test_get_theme_quota_returns_dynamic_limits_and_counts(self, client):
        response = client.get(f"{THEMES_URL}/quota")
        assert response.status_code == 200
        data = response.json()["data"]
        assert "max_total" in data
        assert "max_custom" in data
        assert "total_count" in data
        assert "custom_count" in data
        assert "is_limit_reached" in data
        assert data["max_total"] == 9
        assert data["max_custom"] == 6
        assert data["total_count"] >= 3


class TestApplyThemeE2E:
    def test_non_admin_cannot_apply_theme(self, client, user_headers):
        res = client.get(THEMES_URL)
        theme_id = res.json()["data"][0]["id"]

        apply_res = client.post(
            f"{THEMES_URL}/{theme_id}/apply",
            headers=user_headers,
        )
        assert apply_res.status_code == 403

    def test_admin_can_apply_theme(self, client, admin_headers):
        res = client.get(THEMES_URL)
        themes = res.json()["data"]
        # Find the Dourado & Ônix theme
        target_theme = next(
            (t for t in themes if "Dourado" in t["name"]),
            themes[0],
        )

        apply_res = client.post(
            f"{THEMES_URL}/{target_theme['id']}/apply",
            headers=admin_headers,
        )
        assert apply_res.status_code == 200
        config_data = apply_res.json()["data"]
        assert config_data["theme_id"] == target_theme["id"]
        assert config_data["color_buttons"] == target_theme["color_buttons"]
        assert config_data["color_bg_primary"] == target_theme["color_bg_primary"]

        # Check that GET /office-config returns the applied colors and theme_id
        cfg_res = client.get(OFFICE_CONFIG_URL)
        assert cfg_res.status_code == 200
        assert cfg_res.json()["data"]["theme_id"] == target_theme["id"]
        assert cfg_res.json()["data"]["color_buttons"] == target_theme["color_buttons"]


@pytest.fixture
def audit_themes(client, db_session):
    """Restore singleton config and remove only themes created by this test."""
    from sqlalchemy import select

    from app.modules.office_config.model import LandingPageTheme, OfficeConfig

    config = db_session.get(OfficeConfig, 1)
    original = {
        column.name: getattr(config, column.name)
        for column in OfficeConfig.__table__.columns
    }
    ids = set(db_session.scalars(select(LandingPageTheme.id)).all())
    yield
    db_session.rollback()
    db_session.expire_all()
    config = db_session.get(OfficeConfig, 1)
    for key, value in original.items():
        setattr(config, key, value)
    db_session.flush()
    for theme in db_session.scalars(select(LandingPageTheme)).all():
        if theme.id not in ids:
            db_session.delete(theme)
    db_session.commit()


@pytest.mark.usefixtures("audit_themes")
class TestThemeCrossAudit:
    def test_tc_s1_01_predefined_put_returns_403_and_preserves_theme(
        self, client, admin_headers
    ):
        original = next(
            t for t in client.get(THEMES_URL).json()["data"] if t["is_predefined"]
        )
        response = client.put(
            f"{THEMES_URL}/{original['id']}",
            headers=admin_headers,
            json={"name": "Overwritten", "color_buttons": "#123456"},
        )
        assert response.status_code == 403
        assert response.json()["error"]["code"] == "PREDEFINED_THEME_UPDATE_NOT_ALLOWED"
        actual = next(
            t
            for t in client.get(THEMES_URL).json()["data"]
            if t["id"] == original["id"]
        )
        assert actual == original

    def test_tc_s1_02_http_quota_rejects_seventh_creation_and_duplicate(
        self, client, admin_headers
    ):
        quota = client.get(f"{THEMES_URL}/quota").json()["data"]
        assert quota["custom_count"] == 0, (
            "Run E2E against a dedicated empty test database"
        )
        for index in range(6):
            response = client.post(
                THEMES_URL,
                headers=admin_headers,
                json=valid_theme_payload(f"Audit {index}"),
            )
            assert response.status_code == 201
        quota = client.get(f"{THEMES_URL}/quota").json()["data"]
        assert (
            quota["custom_count"],
            quota["total_count"],
            quota["is_limit_reached"],
        ) == (6, 9, True)
        official = next(
            t for t in client.get(THEMES_URL).json()["data"] if t["is_predefined"]
        )
        for path, payload in [
            (THEMES_URL, valid_theme_payload("Seventh")),
            (f"{THEMES_URL}/{official['id']}/duplicate", {}),
        ]:
            response = client.post(path, headers=admin_headers, json=payload)
            assert response.status_code == 400
            assert response.json()["error"]["code"] == "THEME_LIMIT_EXCEEDED"
        assert client.get(f"{THEMES_URL}/quota").json()["data"] == quota

    def test_tc_s1_03_deleting_active_custom_theme_keeps_colors_and_clears_fk(
        self, client, admin_headers
    ):
        payload = valid_theme_payload("Active audit theme")
        payload.update(
            system_uses_landing_buttons=False,
            color_buttons_system="#abc",
            color_buttons_system_hover="#12345678",
            color_buttons_system_text="#FFFFFF",
        )
        created = client.post(THEMES_URL, headers=admin_headers, json=payload)
        assert created.status_code == 201
        theme_id = created.json()["data"]["id"]
        applied = client.post(f"{THEMES_URL}/{theme_id}/apply", headers=admin_headers)
        assert applied.status_code == 200
        before = applied.json()["data"]
        assert before["theme_id"] == theme_id
        assert (
            client.delete(f"{THEMES_URL}/{theme_id}", headers=admin_headers).status_code
            == 204
        )
        response = client.get(OFFICE_CONFIG_URL)
        assert response.status_code == 200
        assert response.json()["data"] == {**before, "theme_id": None}

    @pytest.mark.parametrize("uses_landing", [True, False])
    @pytest.mark.parametrize("color", ["#AbC", "#123456", "#12345680"])
    def test_tc_s1_04_theme_system_buttons_roundtrip(
        self, client, admin_headers, uses_landing, color
    ):
        colors = {
            key: color
            for key in [
                "color_buttons_system",
                "color_buttons_system_hover",
                "color_buttons_system_text",
            ]
        }
        colors["system_uses_landing_buttons"] = uses_landing
        created = client.post(
            THEMES_URL, headers=admin_headers, json={**valid_theme_payload(), **colors}
        )
        assert created.status_code == 201
        theme_id = created.json()["data"]["id"]
        for key, value in colors.items():
            assert created.json()["data"][key] == value
        response = client.post(f"{THEMES_URL}/{theme_id}/apply", headers=admin_headers)
        assert response.status_code == 200
        saved = client.get(OFFICE_CONFIG_URL).json()["data"]
        for key, value in colors.items():
            assert saved[key] == value

    @pytest.mark.parametrize(
        "key",
        [
            "color_buttons_system",
            "color_buttons_system_hover",
            "color_buttons_system_text",
        ],
    )
    @pytest.mark.parametrize("color", ["rgb(0,0,0)", "#12345", "#GGGGGG"])
    def test_tc_s1_04_theme_rejects_invalid_hex_on_create_and_update(
        self, client, admin_headers, key, color
    ):
        created = client.post(
            THEMES_URL, headers=admin_headers, json=valid_theme_payload()
        )
        assert created.status_code == 201
        original = created.json()["data"]
        response = client.post(
            THEMES_URL,
            headers=admin_headers,
            json={**valid_theme_payload(), key: color},
        )
        assert response.status_code == 422
        response = client.put(
            f"{THEMES_URL}/{original['id']}", headers=admin_headers, json={key: color}
        )
        assert response.status_code == 422
        actual = next(
            t
            for t in client.get(THEMES_URL).json()["data"]
            if t["id"] == original["id"]
        )
        assert actual == original

    @pytest.mark.parametrize("role", ["anonymous", "collaborator"])
    @pytest.mark.parametrize(
        "method, suffix",
        [
            ("POST", ""),
            ("PUT", "/{id}"),
            ("DELETE", "/{id}"),
            ("POST", "/{id}/duplicate"),
            ("POST", "/{id}/apply"),
        ],
    )
    def test_tc_s1_05_mutations_require_admin(
        self, client, admin_headers, user_headers, role, method, suffix
    ):
        created = client.post(
            THEMES_URL, headers=admin_headers, json=valid_theme_payload()
        )
        assert created.status_code == 201
        theme_id = created.json()["data"]["id"]
        before = client.get(THEMES_URL).json()["data"]
        config = client.get(OFFICE_CONFIG_URL).json()["data"]
        payload = (
            valid_theme_payload()
            if suffix == ""
            else ({"name": "Forbidden"} if method == "PUT" else {})
        )
        response = client.request(
            method,
            THEMES_URL + suffix.format(id=theme_id),
            json=payload,
            headers={} if role == "anonymous" else user_headers,
        )
        assert response.status_code == (401 if role == "anonymous" else 403)
        assert client.get(THEMES_URL).json()["data"] == before
        assert client.get(OFFICE_CONFIG_URL).json()["data"] == config

    def test_duplicate_copies_all_colors_without_overwriting_official(
        self, client, admin_headers
    ):
        original = next(
            t for t in client.get(THEMES_URL).json()["data"] if t["is_predefined"]
        )
        response = client.post(
            f"{THEMES_URL}/{original['id']}/duplicate", headers=admin_headers
        )
        assert response.status_code == 201
        copy = response.json()["data"]
        assert copy["id"] != original["id"]
        assert copy["name"].endswith("(Cópia)")
        assert copy["is_predefined"] is False
        for key in [
            k
            for k in original
            if k.startswith("color") or k == "system_uses_landing_buttons"
        ]:
            assert copy[key] == original[key]
