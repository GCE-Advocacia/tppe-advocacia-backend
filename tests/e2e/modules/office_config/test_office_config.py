import pytest
from sqlalchemy import delete

from app.modules.office_config.model import OfficeConfig

OFFICE_CONFIG_URL = "/api/v1/office-config"


@pytest.fixture(autouse=True)
def reset_office_config(db_session, client):
    db_session.execute(delete(OfficeConfig))
    db_session.add(OfficeConfig(id=1, differentials=[], areas_of_practice=[]))
    db_session.commit()
    yield
    db_session.execute(delete(OfficeConfig))
    db_session.add(OfficeConfig(id=1, differentials=[], areas_of_practice=[]))
    db_session.commit()


class TestGetOfficeConfig:
    def test_returns_200_without_authentication(self, client):
        response = client.get(OFFICE_CONFIG_URL)
        assert response.status_code == 200

    def test_response_has_success_true(self, client):
        response = client.get(OFFICE_CONFIG_URL)
        assert response.json()["success"] is True

    def test_returns_default_data_before_any_patch(self, client):
        data = client.get(OFFICE_CONFIG_URL).json()["data"]
        assert data["id"] == 1
        assert data["differentials"] == []
        assert data["areas_of_practice"] == []
        assert data["office_name"] is None

    def test_all_expected_fields_present(self, client):
        data = client.get(OFFICE_CONFIG_URL).json()["data"]
        expected_fields = [
            "id",
            "office_name",
            "cnpj",
            "address",
            "phone",
            "email",
            "instagram_url",
            "linkedin_url",
            "whatsapp_url",
            "website_url",
            "hero_title",
            "hero_subtitle",
            "hero_image_url",
            "about_title",
            "about_description",
            "about_image_url",
            "lawyer_name",
            "lawyer_oab",
            "lawyer_description",
            "lawyer_image_url",
            "differentials",
            "areas_of_practice",
            "hero_image_position",
            "about_image_position",
            "lawyer_image_position",
            "color",
            "color_bg_primary",
            "color_bg_secondary",
            "color_bg_sobre",
            "color_buttons",
            "color_title_primary",
            "color_title_secondary",
            "color_text_primary",
            "color_text_secondary",
            "color_link_primary",
            "color_link_secondary",
        ]
        for field in expected_fields:
            assert field in data, f"Missing field: {field}"


class TestPatchOfficeConfig:
    def test_returns_401_without_authentication(self, client):
        response = client.patch(OFFICE_CONFIG_URL, json={"office_name": "Test"})
        assert response.status_code == 401

    def test_returns_403_for_non_admin_user(self, client, user_headers):
        response = client.patch(
            OFFICE_CONFIG_URL, json={"office_name": "Test"}, headers=user_headers
        )
        assert response.status_code == 403

    def test_admin_can_update_institutional_fields(self, client, admin_headers):
        response = client.patch(
            OFFICE_CONFIG_URL,
            json={"office_name": "Escritório Silva", "cnpj": "12.345.678/0001-99"},
            headers=admin_headers,
        )
        assert response.status_code == 200
        data = response.json()["data"]
        assert data["office_name"] == "Escritório Silva"
        assert data["cnpj"] == "12.345.678/0001-99"

    def test_admin_can_update_hero_fields(self, client, admin_headers):
        response = client.patch(
            OFFICE_CONFIG_URL,
            json={
                "hero_title": "Defenda seus direitos",
                "hero_subtitle": "Com quem entende",
            },
            headers=admin_headers,
        )
        assert response.status_code == 200
        data = response.json()["data"]
        assert data["hero_title"] == "Defenda seus direitos"
        assert data["hero_subtitle"] == "Com quem entende"

    def test_admin_can_update_differentials(self, client, admin_headers):
        items = [
            {"title": "Experiência", "description": "20 anos de atuação"},
            {"title": "Resultados", "description": "Alta taxa de êxito"},
            {"title": "Atendimento", "description": "Personalizado e humanizado"},
        ]
        response = client.patch(
            OFFICE_CONFIG_URL, json={"differentials": items}, headers=admin_headers
        )
        assert response.status_code == 200
        assert response.json()["data"]["differentials"] == items

    def test_admin_can_update_areas_of_practice(self, client, admin_headers):
        areas = [{"title": "Direito Civil", "description": "Contratos e família"}]
        response = client.patch(
            OFFICE_CONFIG_URL, json={"areas_of_practice": areas}, headers=admin_headers
        )
        assert response.status_code == 200
        assert response.json()["data"]["areas_of_practice"] == areas

    def test_partial_update_preserves_other_fields(self, client, admin_headers):
        client.patch(
            OFFICE_CONFIG_URL,
            json={"cnpj": "12.345.678/0001-99"},
            headers=admin_headers,
        )
        response = client.patch(
            OFFICE_CONFIG_URL,
            json={"office_name": "Novo Nome"},
            headers=admin_headers,
        )
        data = response.json()["data"]
        assert data["office_name"] == "Novo Nome"
        assert data["cnpj"] == "12.345.678/0001-99"

    def test_omitted_fields_not_overwritten_with_none(self, client, admin_headers):
        client.patch(
            OFFICE_CONFIG_URL,
            json={"hero_title": "Título Original"},
            headers=admin_headers,
        )
        client.patch(
            OFFICE_CONFIG_URL,
            json={"office_name": "Escritório"},
            headers=admin_headers,
        )
        data = client.get(OFFICE_CONFIG_URL).json()["data"]
        assert data["hero_title"] == "Título Original"

    def test_get_reflects_latest_patch(self, client, admin_headers):
        client.patch(
            OFFICE_CONFIG_URL,
            json={"lawyer_name": "Dr. Carlos Mendes", "lawyer_oab": "OAB/DF 12345"},
            headers=admin_headers,
        )
        data = client.get(OFFICE_CONFIG_URL).json()["data"]
        assert data["lawyer_name"] == "Dr. Carlos Mendes"
        assert data["lawyer_oab"] == "OAB/DF 12345"

    def test_image_positions_default_to_null(self, client):
        data = client.get(OFFICE_CONFIG_URL).json()["data"]
        assert data["hero_image_position"] is None
        assert data["about_image_position"] is None
        assert data["lawyer_image_position"] is None

    def test_admin_can_update_image_positions(self, client, admin_headers):
        response = client.patch(
            OFFICE_CONFIG_URL,
            json={
                "hero_image_position": "30,70",
                "about_image_position": "50,50",
                "lawyer_image_position": "80,20",
            },
            headers=admin_headers,
        )
        assert response.status_code == 200
        data = response.json()["data"]
        assert data["hero_image_position"] == "30,70"
        assert data["about_image_position"] == "50,50"
        assert data["lawyer_image_position"] == "80,20"

    def test_image_position_persists_after_other_update(self, client, admin_headers):
        client.patch(
            OFFICE_CONFIG_URL,
            json={"hero_image_position": "25,75"},
            headers=admin_headers,
        )
        client.patch(
            OFFICE_CONFIG_URL,
            json={"office_name": "Escritório Nova"},
            headers=admin_headers,
        )
        data = client.get(OFFICE_CONFIG_URL).json()["data"]
        assert data["hero_image_position"] == "25,75"

    def test_image_position_rejects_value_exceeding_max_length(
        self, client, admin_headers
    ):
        response = client.patch(
            OFFICE_CONFIG_URL,
            json={"hero_image_position": "123456789012345678901"},
            headers=admin_headers,
        )
        assert response.status_code == 422

    def test_color_defaults_to_null(self, client):
        data = client.get(OFFICE_CONFIG_URL).json()["data"]
        assert data["color"] is None

    def test_admin_can_update_color(self, client, admin_headers):
        response = client.patch(
            OFFICE_CONFIG_URL,
            json={"color": "#1E3A8A"},
            headers=admin_headers,
        )
        assert response.status_code == 200
        data = response.json()["data"]
        assert data["color"] == "#1E3A8A"

    def test_color_persists_after_other_update(self, client, admin_headers):
        client.patch(
            OFFICE_CONFIG_URL,
            json={"color": "#FF5733"},
            headers=admin_headers,
        )
        client.patch(
            OFFICE_CONFIG_URL,
            json={"office_name": "Novo Escritório"},
            headers=admin_headers,
        )
        data = client.get(OFFICE_CONFIG_URL).json()["data"]
        assert data["color"] == "#FF5733"

    def test_color_rejects_value_exceeding_max_length(
        self, client, admin_headers
    ):
        response = client.patch(
            OFFICE_CONFIG_URL,
            json={"color": "x" * 51},
            headers=admin_headers,
        )
        assert response.status_code == 422

    def test_admin_can_update_landing_page_colors(self, client, admin_headers):
        payload = {
            "color_bg_primary": "#0A192F",
            "color_bg_secondary": "#F0F4F8",
            "color_bg_sobre": "#FFFFFF",
            "color_buttons": "#E63946",
            "color_title_primary": "#F1FAEE",
            "color_title_secondary": "#1D3557",
            "color_text_primary": "#F1F1F1",
            "color_text_secondary": "#6B7280",
            "color_link_primary": "#FFFFFF",
            "color_link_secondary": "#661C16",
        }
        response = client.patch(
            OFFICE_CONFIG_URL,
            json=payload,
            headers=admin_headers,
        )
        assert response.status_code == 200
        data = response.json()["data"]
        for key, val in payload.items():
            assert data[key] == val

        # Valida se persiste no GET
        get_res = client.get(OFFICE_CONFIG_URL).json()["data"]
        for key, val in payload.items():
            assert get_res[key] == val
