from pathlib import Path

from krakenlink.bridge.__main__ import load_config


def test_pi_template_renders_as_bridge_config(tmp_path):
    template = Path(__file__).parents[1] / 'deploy/pi/bridge.pi.toml.in'
    rendered = template.read_text()
    for key, value in {'@KRAKEN_ROOT@': '/tmp/kraken', '@AIR_PORT@': '/dev/air', '@FC_PORT@': '/dev/cube', '@LOG_DIR@': '/tmp/logs'}.items():
        rendered = rendered.replace(key, value)
    config = tmp_path / 'bridge.toml'
    config.write_text(rendered)
    parsed = load_config(config)
    assert parsed['transport']['type'] == 'espnow_uart'
    assert parsed['fc']['connection'] == '/dev/cube'


def test_pi_units_render_without_placeholders_and_launcher_is_python_only():
    deploy = Path(__file__).parents[1] / 'deploy/pi'
    replacements = {
        '@KRAKEN_ROOT@': '/home/pi/krakensdr',
        '@CONDA_SH@': '/home/pi/miniforge3/etc/profile.d/conda.sh',
        '@WORKDIR@': '/home/pi/krakenlink',
        '@VENV@': '/home/pi/krakenlink/.venv',
        '@CONFIG@': '/home/pi/krakenlink/bridge.toml',
    }
    for name in ('krakensdr.service', 'krakenlink-bridge.service.in'):
        rendered = (deploy / name).read_text()
        for key, value in replacements.items():
            rendered = rendered.replace(key, value)
        assert '@' not in rendered

    launcher = (deploy / 'kraken-headless.sh').read_text().lower()
    assert all(name not in launcher for name in ('php', 'node', 'miniserve'))
