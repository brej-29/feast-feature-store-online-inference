import importlib

import pytest


@pytest.mark.parametrize(
    "module_path",
    [
        "feature_repo.entities",
        "feature_repo.data_sources",
        "feature_repo.feature_views",
        "feature_repo.feature_services",
        "feature_repo.on_demand_feature_views",
    ],
)
def test_feature_repo_modules_import(module_path: str):
    importlib.import_module(module_path)