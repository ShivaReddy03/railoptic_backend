import importlib
import unittest


class RoboflowImportTest(unittest.TestCase):
    def test_module_imports_without_inference_sdk(self):
        module = importlib.import_module("app.services.roboflow")
        self.assertTrue(hasattr(module, "RoboflowInferenceError"))
        self.assertTrue(hasattr(module, "infer_image"))


if __name__ == "__main__":
    unittest.main()
