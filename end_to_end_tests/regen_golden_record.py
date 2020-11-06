""" Regenerate golden-record """
import shutil
import sys
from pathlib import Path

from typer.testing import CliRunner

from openapi_python_client.cli import app

if __name__ == "__main__":
    runner = CliRunner()
    openapi_path = Path(__file__).parent / "openapi.json"

    output_path = Path.cwd() / "my-test-api-client"

    custom = len(sys.argv) >= 2 and sys.argv[1] == "custom"
    if custom:
        gr_path = Path(__file__).parent / "golden-record-custom"
    else:
        gr_path = Path(__file__).parent / "golden-record"

    shutil.rmtree(gr_path, ignore_errors=True)
    shutil.rmtree(output_path, ignore_errors=True)
    config_path = Path(__file__).parent / "config.yml"

    if custom:
        result = runner.invoke(
            app,
            [
                f"--config={config_path}",
                "generate",
                f"--path={openapi_path}",
                "--custom-template-path=end_to_end_tests/test_custom_templates",
            ],
        )
    else:
        result = runner.invoke(app, [f"--config={config_path}", "generate", f"--path={openapi_path}"])

    if result.stdout:
        print(result.stdout)
    if result.exception:
        raise result.exception
    output_path.rename(gr_path)
