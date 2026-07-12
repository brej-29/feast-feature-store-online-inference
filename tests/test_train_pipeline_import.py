import importlib


def test_train_model_module_imports():
    # Basic smoke test that the training pipeline module imports successfully.
    importlib.import_module("pipelines.train_model")