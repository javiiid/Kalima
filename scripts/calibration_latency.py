"""Measure where a calibration sample call actually spends its time.

The preview felt "stuck" and then failed with "Request timed out.", which can
come from the provider, from our own client timeout, or from a response that
the provider truncated at ``max_tokens``. Guessing between those three has cost
more time than measuring them, so this script sends the same request the
calibration preview sends and prints the stages separately.

Usage (real provider, costs a fraction of a cent):

    python -m scripts.calibration_latency --model deepseek-v4.1-flash
    python -m scripts.calibration_latency --model gpt-5.6-luna --units 3

Streaming is measured too: time-to-first-token is the number a user actually
perceives, and a non-streaming call shows nothing until the whole answer lands.
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from concurrent.futures import ThreadPoolExecutor

from app.calibration.engine import SYSTEM, TONES, slots_for, token_estimate
from app.core.config import get_openai_config
from app.core.models import model_request


SAMPLE = (
    "The lamp on the desk had been burning since dusk, and Mara had not moved it. "
    "She read the same paragraph four times, hearing the words without keeping them, "
    "while the rain turned the window into a sheet of soft, wavering light. "
    "\"You are not listening,\" said Idris from the doorway. He did not sound angry. "
    "He sounded like a man reporting the weather. She set the page down, smoothed it "
    "flat with her palm, and said nothing at all, because the truth was that she had "
    "been listening to the rain instead, and to the small metallic tick of the lamp "
    "cooling, and to the house settling around them like an animal going to sleep."
)


def build_request(model, max_tokens):
    parts, slots = slots_for(f"<p>{SAMPLE}</p>")
    messages = [
        {"role": "system", "content": SYSTEM.format(source_language="English", target_language="Persian", tone=TONES["literary"]["rules"])},
        {"role": "user", "content": json.dumps({"context": "", "slots": slots, "glossary": [], "approved_style_guidance": ""}, ensure_ascii=False)},
    ]
    return {**model_request(model), "messages": messages, "temperature": 0.2, "max_tokens": max_tokens}, slots


def probe(model, max_tokens, timeout, stream):
    from openai import OpenAI

    client = OpenAI(**get_openai_config(), max_retries=0, timeout=timeout)
    request, slots = build_request(model, max_tokens)
    estimate = token_estimate(request)
    started = time.monotonic()
    first_token = None
    chunks = 0
    content = []
    try:
        if stream:
            response = client.chat.completions.create(**request, stream=True, stream_options={"include_usage": True})
            finish, usage = None, None
            for event in response:
                if event.choices:
                    delta = event.choices[0].delta
                    if delta and delta.content:
                        if first_token is None:
                            first_token = time.monotonic() - started
                        chunks += 1
                        content.append(delta.content)
                    if event.choices[0].finish_reason:
                        finish = event.choices[0].finish_reason
                if getattr(event, "usage", None):
                    usage = event.usage
        else:
            response = client.chat.completions.create(**request)
            first_token = time.monotonic() - started
            content.append(response.choices[0].message.content or "")
            finish = response.choices[0].finish_reason
            usage = getattr(response, "usage", None)
    except BaseException as exc:
        return {"model": model, "ok": False, "error": f"{type(exc).__name__}: {exc}",
                "seconds": round(time.monotonic() - started, 2), "input_tokens": estimate}
    total = time.monotonic() - started
    text = "".join(content)
    try:
        parsed = json.loads(text.strip().removeprefix("```json").removeprefix("```").removesuffix("```").strip())
        kept = len(parsed.get("translations", []))
    except (ValueError, TypeError):
        parsed, kept = None, 0
    return {
        "model": model,
        "ok": True,
        "seconds": round(total, 2),
        "first_token_seconds": round(first_token, 2) if first_token is not None else None,
        "stream_chunks": chunks if stream else None,
        "slots": len(slots),
        "slots_returned": kept,
        "finish_reason": finish,
        "max_tokens": max_tokens,
        "input_tokens_estimate": estimate,
        "output_tokens": getattr(usage, "completion_tokens", None),
        "prompt_tokens": getattr(usage, "prompt_tokens", None),
        "output_chars": len(text),
    }


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--model", default="deepseek-v4.1-flash")
    parser.add_argument("--units", type=int, default=3, help="how many preview units run (concurrently)")
    parser.add_argument("--max-tokens", type=int, default=4096)
    parser.add_argument("--timeout", type=float, default=600.0)
    parser.add_argument("--stream", action="store_true", help="also measure streaming time-to-first-token")
    args = parser.parse_args(argv)

    print(f"model={args.model} units={args.units} max_tokens={args.max_tokens} timeout={args.timeout}s")
    started = time.monotonic()
    with ThreadPoolExecutor(max_workers=max(1, args.units)) as pool:
        results = list(pool.map(lambda _: probe(args.model, args.max_tokens, args.timeout, False), range(args.units)))
    wall = time.monotonic() - started
    for index, result in enumerate(results, 1):
        print(f"  unit {index}: {json.dumps(result, ensure_ascii=False)}")
    print(f"parallel wall clock: {wall:.2f}s")

    if args.stream:
        result = probe(args.model, args.max_tokens, args.timeout, True)
        print(f"stream: {json.dumps(result, ensure_ascii=False)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
