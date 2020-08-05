""" Generate modern Python clients from OpenAPI """
from __future__ import annotations

import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any, Dict, Optional, Sequence, Union

import httpcore
import httpx
from jinja2 import Environment, PackageLoader

from openapi_python_client import utils

from .parser import GeneratorData, import_string_from_reference
from .parser.errors import GeneratorError

if sys.version_info.minor == 7:  # version did not exist in 3.7, need to use a backport
    from importlib_metadata import version
else:
    from importlib.metadata import version  #type: ignore


__version__ = version(__package__)

project_name_override: Optional[str] = None
package_name_override: Optional[str] = None


def _get_project_for_url_or_path(url: Optional[str], path: Optional[Path]) -> Union[_Project, GeneratorError]:
    data_dict = _get_document(url=url, path=path)
    if isinstance(data_dict, GeneratorError):
        return data_dict
    openapi = GeneratorData.from_dict(data_dict)
    if isinstance(openapi, GeneratorError):
        return openapi
    return _Project(openapi=openapi)


def create_new_client(*, url: Optional[str], path: Optional[Path]) -> Sequence[GeneratorError]:
    """
    Generate the client library

    Returns:
         A list containing any errors encountered when generating.
    """
    project = _get_project_for_url_or_path(url=url, path=path)
    if isinstance(project, GeneratorError):
        return [project]
    return project.build()


def update_existing_client(*, url: Optional[str], path: Optional[Path]) -> Sequence[GeneratorError]:
    """
    Update an existing client library

    Returns:
         A list containing any errors encountered when generating.
    """
    project = _get_project_for_url_or_path(url=url, path=path)
    if isinstance(project, GeneratorError):
        return [project]
    return project.update()


def _get_document(*, url: Optional[str], path: Optional[Path]) -> Union[Dict[str, Any], GeneratorError]:
    yaml_bytes: bytes
    if url is not None and path is not None:
        return GeneratorError(header="Provide URL or Path, not both.")
    if url is not None:
        try:
            response = httpx.get(url)
            yaml_bytes = response.content
        except (httpx.HTTPError, httpcore.NetworkError):
            return GeneratorError(header="Could not get OpenAPI document from provided URL")
    elif path is not None:
        yaml_bytes = path.read_bytes()
    else:
        return GeneratorError(header="No URL or Path provided")
    try:
        return yaml.safe_load(yaml_bytes)
    except yaml.YAMLError:
        return GeneratorError(header="Invalid YAML from provided source")


class _Project:
    TEMPLATE_FILTERS = {"snakecase": utils.snake_case}
    project_name_override: Optional[str] = None
    package_name_override: Optional[str] = None

    def __init__(self, *, openapi: GeneratorData) -> None:
        self.openapi: GeneratorData = openapi
        self.env: Environment = Environment(loader=PackageLoader(__package__), trim_blocks=True, lstrip_blocks=True)

        self.project_name: str = self.project_name_override or f"{openapi.title.replace(' ', '-').lower()}-client"
        self.project_dir: Path = Path.cwd() / self.project_name

        self.package_name: str = self.package_name_override or self.project_name.replace("-", "_")
        self.package_dir: Path = self.project_dir / self.package_name
        self.package_description = f"A client library for accessing {self.openapi.title}"

        self.env.filters.update(self.TEMPLATE_FILTERS)

    def build(self) -> Sequence[GeneratorError]:
        """ Create the project from templates """

        print(f"Generating {self.project_name}")
        try:
            self.project_dir.mkdir()
        except FileExistsError:
            return [GeneratorError(detail="Directory already exists. Delete it or use the update command.")]
        self._create_package()
        self._build_metadata()
        self._build_models()
        self._build_api()
        self._reformat()
        return self._get_errors()

    def update(self) -> Sequence[GeneratorError]:
        """ Update an existing project """

        if not self.package_dir.is_dir():
            raise FileNotFoundError()
        print(f"Updating {self.project_name}")
        shutil.rmtree(self.package_dir)
        self._create_package()
        self._build_models()
        self._build_api()
        self._reformat()
        return self._get_errors()

    def _reformat(self) -> None:
        subprocess.run(
            "isort .", cwd=self.project_dir, shell=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
        )
        subprocess.run("black .", cwd=self.project_dir, shell=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)

    def _get_errors(self) -> Sequence[GeneratorError]:
        errors = []
        for collection in self.openapi.endpoint_collections_by_tag.values():
            errors.extend(collection.parse_errors)
        errors.extend(self.openapi.schemas.errors)
        return errors

    def _create_package(self) -> None:
        self.package_dir.mkdir()
        # Package __init__.py
        package_init = self.package_dir / "__init__.py"

        package_init_template = self.env.get_template("package_init.pyi")
        package_init.write_text(package_init_template.render(description=self.package_description))

        pytyped = self.package_dir / "py.typed"
        pytyped.write_text("# Marker file for PEP 561")

    def _build_metadata(self) -> None:
        # Create a pyproject.toml file
        pyproject_template = self.env.get_template("pyproject.toml")
        pyproject_path = self.project_dir / "pyproject.toml"
        pyproject_path.write_text(
            pyproject_template.render(
                project_name=self.project_name, package_name=self.package_name, description=self.package_description
            )
        )

        # README.md
        readme = self.project_dir / "README.md"
        readme_template = self.env.get_template("README.md")
        readme.write_text(
            readme_template.render(
                project_name=self.project_name, description=self.package_description, package_name=self.package_name
            )
        )

        # .gitignore
        git_ignore_path = self.project_dir / ".gitignore"
        git_ignore_template = self.env.get_template(".gitignore")
        git_ignore_path.write_text(git_ignore_template.render())

    def _build_models(self) -> None:
        # Generate models
        models_dir = self.package_dir / "models"
        models_dir.mkdir()
        models_init = models_dir / "__init__.py"
        imports = []

        types_template = self.env.get_template("types.py")
        types_path = models_dir / "types.py"
        types_path.write_text(types_template.render())

        model_template = self.env.get_template("model.pyi")
        for model in self.openapi.schemas.models.values():
            module_path = models_dir / f"{model.reference.module_name}.py"
            module_path.write_text(model_template.render(model=model))
            imports.append(import_string_from_reference(model.reference))

        # Generate enums
        enum_template = self.env.get_template("enum.pyi")
        for enum in self.openapi.enums.values():
            module_path = models_dir / f"{enum.reference.module_name}.py"
            module_path.write_text(enum_template.render(enum=enum))
            imports.append(import_string_from_reference(enum.reference))

        models_init_template = self.env.get_template("models_init.pyi")
        models_init.write_text(models_init_template.render(imports=imports))

    def _build_api(self) -> None:
        # Generate Client
        client_path = self.package_dir / "client.py"
        client_template = self.env.get_template("client.pyi")
        client_path.write_text(client_template.render())

        # Generate endpoints
        api_dir = self.package_dir / "api"
        api_dir.mkdir()
        api_init = api_dir / "__init__.py"
        api_init.write_text('""" Contains synchronous methods for accessing the API """')

        async_api_dir = self.package_dir / "async_api"
        async_api_dir.mkdir()
        async_api_init = async_api_dir / "__init__.py"
        async_api_init.write_text('""" Contains async methods for accessing the API """')

        api_errors = self.package_dir / "errors.py"
        errors_template = self.env.get_template("errors.pyi")
        api_errors.write_text(errors_template.render())

        endpoint_template = self.env.get_template("endpoint_module.pyi")
        async_endpoint_template = self.env.get_template("async_endpoint_module.pyi")
        for tag, collection in self.openapi.endpoint_collections_by_tag.items():
            module_path = api_dir / f"{tag}.py"
            module_path.write_text(endpoint_template.render(collection=collection))
            async_module_path = async_api_dir / f"{tag}.py"
            async_module_path.write_text(async_endpoint_template.render(collection=collection))
