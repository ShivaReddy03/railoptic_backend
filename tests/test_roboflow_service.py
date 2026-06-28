import importlib
import unittest


class RoboflowImportTest(unittest.TestCase):
    def test_module_imports_without_inference_sdk(self):
        module = importlib.import_module("app.services.roboflow")
        self.assertTrue(hasattr(module, "RoboflowInferenceError"))
        self.assertTrue(hasattr(module, "infer_image"))

    def test_summarizes_workflow_outputs_payload(self):
        module = importlib.import_module("app.services.roboflow")
        payload = {
            "outputs": [
                {
                    "hazard_predictions_in_roi": {
                        "predictions": [
                            {"class": "elephant", "confidence": 0.8056640625, "risk_level": "high"}
                        ]
                    },
                    "hazard_count": 1,
                    "risk_level": "high",
                }
            ],
            "profiler_trace": [],
        }

        summary = module._summarize_inference_response(payload)

        self.assertEqual(summary["hazard_count"], 1)
        self.assertEqual(summary["risk_level"], "high")
        self.assertEqual(summary["top_prediction"]["class"], "elephant")
        self.assertAlmostEqual(summary["top_prediction"]["confidence"], 0.8056640625)


if __name__ == "__main__":
    unittest.main()
