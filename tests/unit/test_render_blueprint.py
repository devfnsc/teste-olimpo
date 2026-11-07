"""Garante que o Blueprint continue pronto para a demonstração no Render."""

from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[2]


def _blueprint() -> dict:
    return yaml.safe_load((ROOT / "render.yaml").read_text(encoding="utf-8"))


def _services() -> dict[str, dict]:
    return {service["name"]: service for service in _blueprint()["services"]}


def _env(service: dict) -> dict[str, dict]:
    return {item["key"]: item for item in service["envVars"] if "key" in item}


def test_blueprint_tem_api_e_painel_com_dockerfiles_e_healthchecks() -> None:
    services = _services()
    assert set(services) == {"olimpo-api", "olimpo-panel"}

    for service in services.values():
        assert (ROOT / service["dockerfilePath"]).is_file()
        assert (ROOT / service.get("dockerContext", ".")).is_dir()
        assert service.get("healthCheckPath")

    assert services["olimpo-api"]["healthCheckPath"] == "/health"
    assert services["olimpo-panel"]["healthCheckPath"] == "/login"


def test_painel_recebe_url_publica_e_token_da_api() -> None:
    services = _services()
    api_env = _env(services["olimpo-api"])
    panel_env = _env(services["olimpo-panel"])

    assert api_env["API_TOKEN"]["generateValue"] is True
    assert panel_env["OLIMPO_API_URL"]["fromService"] == {
        "type": "web",
        "name": "olimpo-api",
        "envVarKey": "RENDER_EXTERNAL_URL",
    }
    assert panel_env["OLIMPO_API_TOKEN"]["fromService"] == {
        "type": "web",
        "name": "olimpo-api",
        "envVarKey": "API_TOKEN",
    }


def test_demo_nao_inicia_dispatch_e_nao_grava_segredos_no_yaml() -> None:
    services = _services()
    api_env = _env(services["olimpo-api"])
    panel_env = _env(services["olimpo-panel"])

    assert api_env["DISPATCH_ENABLED"]["value"] == "false"
    assert api_env["GLOBAL_KILL_SWITCH"]["value"] == "true"
    assert api_env["APPRUNCLOUD_API_KEY"]["sync"] is False
    assert api_env["APPRUNCLOUD_ORG_ID"]["sync"] is False
    assert panel_env["PANEL_ACCESS_PASSWORD"]["sync"] is False
    assert panel_env["PANEL_SESSION_SECRET"]["generateValue"] is True


