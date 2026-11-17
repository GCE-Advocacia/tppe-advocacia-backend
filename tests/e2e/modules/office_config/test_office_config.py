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
            "color_buttons_hover",
            "color_buttons_text",
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

    def test_color_rejects_value_exceeding_max_length(self, client, admin_headers):
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
            "color_buttons_hover": "#C5222F",
            "color_buttons_text": "#FFFFFF",
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


class TestSystemButtonColorsAudit:
    """TC-S1-04: OfficeConfig uses PATCH (the existing partial-update contract)."""

    @pytest.mark.parametrize("uses_landing", [True, False])
    @pytest.mark.parametrize("color", ["#AbC", "#123456", "#12345680"])
    def test_roundtrip_all_system_button_fields(
        self, client, admin_headers, uses_landing, color
    ):
        payload = {
            key: color
            for key in [
                "color_buttons_system",
                "color_buttons_system_hover",
                "color_buttons_system_text",
            ]
        }
        payload["system_uses_landing_buttons"] = uses_landing
        response = client.patch(OFFICE_CONFIG_URL, headers=admin_headers, json=payload)
        assert response.status_code == 200
        saved = client.get(OFFICE_CONFIG_URL).json()["data"]
        for key, value in payload.items():
            assert saved[key] == value
        client.patch(
            OFFICE_CONFIG_URL, headers=admin_headers, json={"phone": "11999990000"}
        )
        saved = client.get(OFFICE_CONFIG_URL).json()["data"]
        for key, value in payload.items():
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
    def test_invalid_color_does_not_change_config(
        self, client, admin_headers, key, color
    ):
        before = client.get(OFFICE_CONFIG_URL).json()["data"]
        response = client.patch(
            OFFICE_CONFIG_URL, headers=admin_headers, json={key: color}
        )
        assert response.status_code == 422
        assert client.get(OFFICE_CONFIG_URL).json()["data"] == before


class TestInstitutionalLinksValidation:
    """TC-S3-01: Validação de URLs AnyHttpUrl e Strings Vazias nos Links Institucionais"""

    def test_valid_urls_return_200_and_persist(self, client, admin_headers):
        payload = {
            "linkedin_url": "https://linkedin.com/in/teste",
            "instagram_url": "https://instagram.com/teste",
            "whatsapp_url": "https://wa.me/5561999999999",
            "website_url": "https://escritorio.adv.br",
        }
        response = client.patch(OFFICE_CONFIG_URL, json=payload, headers=admin_headers)
        assert response.status_code == 200
        data = response.json()["data"]
        assert data["linkedin_url"] == "https://linkedin.com/in/teste"
        assert data["instagram_url"] == "https://instagram.com/teste"
        assert data["whatsapp_url"] == "https://wa.me/5561999999999"
        assert data["website_url"] == "https://escritorio.adv.br/"

        # Confirma no GET
        get_data = client.get(OFFICE_CONFIG_URL).json()["data"]
        assert get_data["linkedin_url"] == "https://linkedin.com/in/teste"
        assert get_data["instagram_url"] == "https://instagram.com/teste"
        assert get_data["whatsapp_url"] == "https://wa.me/5561999999999"
        assert get_data["website_url"] == "https://escritorio.adv.br/"

    def test_empty_and_whitespace_strings_coerced_to_none(self, client, admin_headers):
        # Primeiro preenche com URLs válidas
        client.patch(
            OFFICE_CONFIG_URL,
            json={
                "linkedin_url": "https://linkedin.com/in/teste",
                "instagram_url": "https://instagram.com/teste",
                "whatsapp_url": "https://wa.me/5561999999999",
                "website_url": "https://escritorio.adv.br",
                "hero_image_url": "https://cdn.example.com/hero.jpg",
                "about_image_url": "https://cdn.example.com/about.jpg",
                "lawyer_image_url": "https://cdn.example.com/lawyer.jpg",
            },
            headers=admin_headers,
        )

        # Envia strings vazias e com espaços
        payload = {
            "linkedin_url": "",
            "instagram_url": "   ",
            "whatsapp_url": "",
            "website_url": "   ",
            "hero_image_url": "",
            "about_image_url": "   ",
            "lawyer_image_url": "",
        }
        response = client.patch(OFFICE_CONFIG_URL, json=payload, headers=admin_headers)
        assert response.status_code == 200
        data = response.json()["data"]
        assert data["linkedin_url"] is None
        assert data["instagram_url"] is None
        assert data["whatsapp_url"] is None
        assert data["website_url"] is None
        assert data["hero_image_url"] is None
        assert data["about_image_url"] is None
        assert data["lawyer_image_url"] is None

        # Confirma persistência de None no GET
        get_data = client.get(OFFICE_CONFIG_URL).json()["data"]
        assert get_data["linkedin_url"] is None
        assert get_data["instagram_url"] is None
        assert get_data["whatsapp_url"] is None
        assert get_data["website_url"] is None
        assert get_data["hero_image_url"] is None
        assert get_data["about_image_url"] is None
        assert get_data["lawyer_image_url"] is None

    @pytest.mark.parametrize(
        "invalid_field,invalid_url",
        [
            ("linkedin_url", "linkedin.com/in/teste"),
            ("instagram_url", "@meuinsta"),
            ("whatsapp_url", "5561999999999"),
            ("website_url", "ftp://meusite.adv.br"),
            ("hero_image_url", "imagem.png"),
        ],
    )
    def test_invalid_urls_return_422(
        self, client, admin_headers, invalid_field, invalid_url
    ):
        response = client.patch(
            OFFICE_CONFIG_URL,
            json={invalid_field: invalid_url},
            headers=admin_headers,
        )
        assert response.status_code == 422


class TestDifferentialsAndAreasLimits:
    """TC-S3-02: Validação de Limites e Estrutura de diferenciais (máx 3) e areas_of_practice (máx 6)"""

    def test_full_update_3_differentials_and_6_areas_returns_200(
        self, client, admin_headers
    ):
        diffs = [
            {"title": f"Diferencial {i}", "description": f"Descrição {i}"}
            for i in range(1, 4)
        ]
        areas = [
            {"title": f"Área de Atuação {i}", "description": f"Descrição Área {i}"}
            for i in range(1, 7)
        ]
        response = client.patch(
            OFFICE_CONFIG_URL,
            json={"differentials": diffs, "areas_of_practice": areas},
            headers=admin_headers,
        )
        assert response.status_code == 200
        data = response.json()["data"]
        assert len(data["differentials"]) == 3
        assert len(data["areas_of_practice"]) == 6
        assert data["differentials"] == diffs
        assert data["areas_of_practice"] == areas

        # Confirma persistência no GET
        get_data = client.get(OFFICE_CONFIG_URL).json()["data"]
        assert len(get_data["differentials"]) == 3
        assert len(get_data["areas_of_practice"]) == 6

    def test_more_than_3_differentials_returns_422(self, client, admin_headers):
        diffs = [
            {"title": f"Diferencial {i}", "description": f"Descrição {i}"}
            for i in range(1, 5)
        ]
        response = client.patch(
            OFFICE_CONFIG_URL,
            json={"differentials": diffs},
            headers=admin_headers,
        )
        assert response.status_code == 422

    def test_more_than_6_areas_of_practice_returns_422(self, client, admin_headers):
        areas = [
            {"title": f"Área {i}", "description": f"Descrição {i}"} for i in range(1, 8)
        ]
        response = client.patch(
            OFFICE_CONFIG_URL,
            json={"areas_of_practice": areas},
            headers=admin_headers,
        )
        assert response.status_code == 422

    @pytest.mark.parametrize("empty_title", ["", "   "])
    def test_differential_empty_title_returns_422(
        self, client, admin_headers, empty_title
    ):
        response = client.patch(
            OFFICE_CONFIG_URL,
            json={"differentials": [{"title": empty_title, "description": "Desc"}]},
            headers=admin_headers,
        )
        assert response.status_code == 422

    @pytest.mark.parametrize("empty_title", ["", "   "])
    def test_area_empty_title_returns_422(self, client, admin_headers, empty_title):
        response = client.patch(
            OFFICE_CONFIG_URL,
            json={"areas_of_practice": [{"title": empty_title, "description": "Desc"}]},
            headers=admin_headers,
        )
        assert response.status_code == 422

    def test_unknown_field_in_list_item_returns_422(self, client, admin_headers):
        response = client.patch(
            OFFICE_CONFIG_URL,
            json={
                "differentials": [
                    {"title": "Título", "description": "Desc", "extra_prop": "invalid"}
                ]
            },
            headers=admin_headers,
        )
        assert response.status_code == 422

    def test_unknown_field_in_payload_root_returns_422(self, client, admin_headers):
        response = client.patch(
            OFFICE_CONFIG_URL,
            json={"unknown_field_123": "invalido"},
            headers=admin_headers,
        )
        assert response.status_code == 422

    def test_get_office_config_with_legacy_empty_titles_returns_200(
        self, client, db_session
    ):
        from app.modules.office_config.model import OfficeConfig

        config = db_session.get(OfficeConfig, 1)
        config.differentials = [
            {"title": "", "description": "Legado 1"},
            {"id": 99, "title": "", "description": "Legado com id extra"},
        ]
        config.areas_of_practice = [{"title": "", "description": "Area legada"}]
        db_session.commit()

        response = client.get(OFFICE_CONFIG_URL)
        assert response.status_code == 200
        data = response.json()["data"]
        assert len(data["differentials"]) == 2
        assert data["differentials"][0]["title"] == ""
        assert data["differentials"][0]["description"] == "Legado 1"
        assert len(data["areas_of_practice"]) == 1
        assert data["areas_of_practice"][0]["title"] == ""


class TestImagesAndPositionsPersistence:
    """TC-S3-03: Persistência de *_image_url e *_image_position"""

    def test_images_urls_and_positions_persistence(self, client, admin_headers):
        payload = {
            "hero_image_url": "https://assets.example.com/hero.jpg",
            "hero_image_position": "25, 75",
            "about_image_url": "https://assets.example.com/office.jpg",
            "about_image_position": "10, 90",
            "lawyer_image_url": "https://assets.example.com/lawyer.jpg",
            "lawyer_image_position": "80, 20",
        }
        response = client.patch(
            OFFICE_CONFIG_URL,
            json=payload,
            headers=admin_headers,
        )
        assert response.status_code == 200
        data = response.json()["data"]
        assert data["hero_image_url"] == "https://assets.example.com/hero.jpg"
        assert data["hero_image_position"] == "25, 75"
        assert data["about_image_url"] == "https://assets.example.com/office.jpg"
        assert data["about_image_position"] == "10, 90"
        assert data["lawyer_image_url"] == "https://assets.example.com/lawyer.jpg"
        assert data["lawyer_image_position"] == "80, 20"

        # Confirma retorno idêntico no GET público
        get_data = client.get(OFFICE_CONFIG_URL).json()["data"]
        for key, val in payload.items():
            assert get_data[key] == val
