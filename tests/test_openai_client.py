from __future__ import annotations

import unittest

from pydantic import BaseModel

from ai.openai_client import OpenAIStructuredChain


class _Answer(BaseModel):
    value: str


class _Responses:
    def __init__(self) -> None:
        self.request = None

    def parse(self, **kwargs):
        self.request = kwargs
        return type("Response", (), {"output_parsed": _Answer(value="parsed")})()


class _Client:
    def __init__(self) -> None:
        self.responses = _Responses()


class OpenAIStructuredChainTests(unittest.TestCase):
    def test_uses_responses_parse_with_pydantic_schema_and_no_storage(self) -> None:
        client = _Client()
        result = OpenAIStructuredChain("System instructions", "Question: {question}", _Answer, client=client).invoke(
            {"question": "What did I eat?"}
        )
        self.assertEqual(result, _Answer(value="parsed"))
        self.assertEqual(client.responses.request["text_format"], _Answer)
        self.assertFalse(client.responses.request["store"])
        self.assertEqual(client.responses.request["input"][1]["content"], "Question: What did I eat?")


if __name__ == "__main__":
    unittest.main()
