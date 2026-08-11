"""LLM thật dùng OpenAI, thay thế được cho FakeLLM trong app/mock_llm.py.

Lớp OpenAILLM giữ nguyên giao diện của FakeLLM (`generate(prompt) -> response` với
`.text`, `.usage.input_tokens`, `.usage.output_tokens`, `.model`) nên app/agent.py
không cần biết đang chạy provider nào.

Hai điểm giữ lại từ bản fake để cơ chế lab không hỏng:

- Cờ incident `cost_spike` vẫn tác động được, thông qua `max_tokens` cao hơn để câu
  trả lời dài ra thật (thay vì nhân số token một cách giả tạo).
- Khi gọi API lỗi, trả về câu trả lời fallback thay vì ném exception, để một sự cố
  của nhà cung cấp không làm hỏng luồng đo lường của lab. Lỗi được ghi vào
  `finish_reason` để log và trace vẫn truy được.

Token lấy từ `usage` thật trong response, không ước lượng.
"""

from __future__ import annotations

import os
from dataclasses import dataclass

from .incidents import STATE

DEFAULT_MODEL = "gpt-4o-mini"
DEFAULT_MAX_TOKENS = 180
SYSTEM_PROMPT = (
    "You are a concise assistant for an observability lab. "
    "Answer using only the provided Docs. Keep the answer short."
)


@dataclass
class Usage:
    input_tokens: int
    output_tokens: int


@dataclass
class Response:
    text: str
    usage: Usage
    model: str
    finish_reason: str | None = None


class OpenAILLM:
    def __init__(self, model: str | None = None) -> None:
        self.model = model or os.getenv("OPENAI_MODEL", DEFAULT_MODEL)
        self._client = None

    def _get_client(self):
        # Khởi tạo trễ để import app không đòi hỏi API key khi chạy provider fake
        if self._client is None:
            try:
                from openai import OpenAI
            except ImportError as exc:  # pragma: no cover
                raise RuntimeError(
                    "Chưa cài package openai. Chạy: pip install -r requirements.txt"
                ) from exc

            api_key = os.getenv("OPENAI_API_KEY")
            if not api_key:
                raise RuntimeError(
                    "Thiếu OPENAI_API_KEY trong .env. Đặt LLM_PROVIDER=fake nếu muốn "
                    "chạy bằng LLM giả."
                )
            self._client = OpenAI(
                api_key=api_key,
                timeout=float(os.getenv("OPENAI_TIMEOUT_SECONDS", "30")),
                max_retries=int(os.getenv("OPENAI_MAX_RETRIES", "2")),
            )
        return self._client

    def generate(self, prompt: str) -> Response:
        max_tokens = int(os.getenv("OPENAI_MAX_TOKENS", str(DEFAULT_MAX_TOKENS)))
        if STATE["cost_spike"]:
            # Giữ nguyên ý nghĩa của incident: câu trả lời dài ra ⇒ cost tăng thật
            max_tokens *= 4

        try:
            completion = self._get_client().chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": SYSTEM_PROMPT},
                    {"role": "user", "content": prompt},
                ],
                max_tokens=max_tokens,
                temperature=float(os.getenv("OPENAI_TEMPERATURE", "0.2")),
            )
        except Exception as exc:
            # Không để lỗi provider làm sập request; ghi lại lý do để log/trace truy được
            return Response(
                text="Tạm thời không tạo được câu trả lời từ mô hình.",
                usage=Usage(input_tokens=max(20, len(prompt) // 4), output_tokens=0),
                model=self.model,
                finish_reason=f"error:{type(exc).__name__}",
            )

        choice = completion.choices[0]
        usage = completion.usage
        return Response(
            text=(choice.message.content or "").strip(),
            usage=Usage(
                input_tokens=usage.prompt_tokens if usage else 0,
                output_tokens=usage.completion_tokens if usage else 0,
            ),
            model=completion.model,
            finish_reason=choice.finish_reason,
        )


# Giá công khai của OpenAI, USD cho mỗi 1 triệu token.
# Dùng để ước lượng cost khi provider là openai; xem app/agent.py.
PRICING_PER_MTOK = {
    "gpt-4o-mini": {"input": 0.15, "output": 0.60},
    "gpt-4o": {"input": 2.50, "output": 10.00},
    "gpt-4.1-mini": {"input": 0.40, "output": 1.60},
    "gpt-4.1": {"input": 2.00, "output": 8.00},
}


def price_for(model: str) -> dict[str, float]:
    """Trả về đơn giá của model; mặc định theo gpt-4o-mini nếu chưa có trong bảng."""
    for name, price in PRICING_PER_MTOK.items():
        if model.startswith(name):
            return price
    return PRICING_PER_MTOK[DEFAULT_MODEL]
