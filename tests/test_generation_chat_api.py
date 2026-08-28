import json
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from sci_exp.generation import LlamaServerGenerator
from sci_exp.schemas import QueryRecord


class _Response:
    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return None

    def read(self):
        return json.dumps(
            {
                "choices": [{"message": {"content": "接口正常"}}],
                "usage": {"prompt_tokens": 12, "completion_tokens": 2},
            }
        ).encode("utf-8")


class GenerationChatApiTests(unittest.TestCase):
    def test_openai_chat_request_and_response(self):
        generator = LlamaServerGenerator(
            "http://127.0.0.1:8080/v1/chat/completions",
            api_style="openai_chat",
            max_tokens_by_configuration={"C0": 128},
        )
        query = QueryRecord(
            "q", "怎么办", "fire", "single", 3, "zh", False
        ).to_inference_query()
        with patch("urllib.request.urlopen", return_value=_Response()) as mocked:
            result = generator.generate(query, [], configuration="C0")
        request = mocked.call_args.args[0]
        payload = json.loads(request.data.decode("utf-8"))
        self.assertEqual(payload["max_tokens"], 128)
        self.assertEqual(payload["messages"][0]["role"], "user")
        self.assertEqual(result.text, "接口正常")
        self.assertEqual(result.generated_tokens, 2)


if __name__ == "__main__":
    unittest.main()
