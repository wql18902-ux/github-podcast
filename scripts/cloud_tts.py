#!/usr/bin/env python3
"""云 TTS 配置与调用薄层。

密钥只保存到 macOS Keychain。项目内只保存 endpoint/model/voice 等非敏感配置，
默认落在 ~/.config/ai-jarvis/tts-console/config.json。
"""

from __future__ import annotations

import argparse
import base64
import concurrent.futures
import copy
import datetime as dt
import json
import math
import os
import re
import shutil
import subprocess
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
import uuid
from pathlib import Path
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_CONFIG_DIR = Path.home() / ".config" / "ai-jarvis" / "tts-console"
DEFAULT_OUTPUT_DIR = PROJECT_ROOT / "output" / "tts-console"
KEYCHAIN_SERVICE = os.environ.get(
    "TTS_CONSOLE_KEYCHAIN_SERVICE", "ai-jarvis-tts-console"
)

# 自定义 provider 存在 config.json 的独立顶层段，避免被当成一个 provider。
# 键名以 "_" 开头，且自定义 id 的正则不允许以 "_" 开头，天然不会冲突。
CUSTOM_PROVIDERS_KEY = "_custom_providers"

# 支持的协议适配器白名单（与 synthesize() 的分发保持一致）。
ALLOWED_ADAPTERS: tuple[str, ...] = (
    "dashscope",
    "minimax",
    "volc_v1",
    "volc_agent_http",
    "volc_http_v3",
    "volc_audio_http",
    "manual",
    "openai",
    "mimo_tts",
)

# 自定义 provider id：小写字母/数字开头，2-40 位，允许 - 和 _。
_PROVIDER_ID_RE = re.compile(r"[a-z0-9][a-z0-9_-]{1,39}")

# 协议适配器「人话」说明，供前端选择时参考。
ADAPTER_INFO: tuple[dict[str, str], ...] = (
    {
        "id": "openai",
        "label": "OpenAI 兼容",
        "desc": "任何兼容 OpenAI /v1/audio/speech 的服务：OpenAI 官方、各类兼容网关、本地推理服务等。",
    },
    {
        "id": "dashscope",
        "label": "阿里百炼 / 千问",
        "desc": "DashScope SpeechSynthesizer，千问 Qwen-Audio、CosyVoice 系列。",
    },
    {
        "id": "minimax",
        "label": "MiniMax",
        "desc": "MiniMax t2a_v2 接口（TokenHub 转售同样走这里）。",
    },
    {
        "id": "volc_v1",
        "label": "火山旧版 V1",
        "desc": "火山 openspeech v1/tts，用 AppID + Access Token，需要额外参数 appid / cluster。",
    },
    {
        "id": "volc_http_v3",
        "label": "火山 v3（豆包）",
        "desc": "火山 openspeech v3 unidirectional 流式接口，豆包语音合成 / 声音复刻。",
    },
    {
        "id": "volc_agent_http",
        "label": "火山 Agent Plan",
        "desc": "火山 Agent Plan 独立 Key，按 AFP 计费。",
    },
    {
        "id": "volc_audio_http",
        "label": "火山音频生成",
        "desc": "火山音频生成 create 接口，支持参考音频，按秒计费。",
    },
    {
        "id": "mimo_tts",
        "label": "小米 MiMo TTS",
        "desc": "MiMo-V2.5-TTS 系列：chat.completions + audio 字段返回 base64 音频，非 OpenAI /audio/speech 协议。",
    },
    {
        "id": "manual",
        "label": "仅存配置",
        "desc": "只保存配置，不参与直接合成（例如音色设计类接口）。",
    },
)

PROVIDER_PRESETS: dict[str, dict[str, Any]] = {
    "qwen": {
        "label": "千问 Qwen-Audio Plus",
        "free_quota": "10K chars",
        "quota_note": "截图有效期至 2026-10-12",
        "adapter": "dashscope",
        "endpoint": "https://dashscope.aliyuncs.com/api/v1/services/audio/tts/SpeechSynthesizer",
        "model": "qwen-audio-3.0-tts-plus",
        "voice": "longanlingxin",
        "extra": {
            "format": "mp3",
            "sample_rate": 24000,
            "rate": 1.0,
            "free_limit_chars": 10000,
            "free_used_chars": 818,
            "free_remaining_chars": 9182,
            "free_expires_at": "2026-10-12T00:00:00+08:00",
            "allow_overage": False,
        },
    },
    "qwen_flash": {
        "label": "千问 Qwen-Audio Flash",
        "free_quota": "10K chars",
        "quota_note": "截图有效期至 2026-10-12",
        "adapter": "dashscope",
        "endpoint": "https://dashscope.aliyuncs.com/api/v1/services/audio/tts/SpeechSynthesizer",
        "model": "qwen-audio-3.0-tts-flash",
        "voice": "longanfengyue",
        "extra": {
            "format": "mp3",
            "sample_rate": 24000,
            "rate": 1.0,
            "free_limit_chars": 10000,
            "free_used_chars": 409,
            "free_remaining_chars": 9591,
            "free_expires_at": "2026-10-12T00:00:00+08:00",
            "allow_overage": False,
        },
    },
    "cosyvoice": {
        "label": "CosyVoice 免费音色",
        "free_quota": "10K chars",
        "quota_note": "截图显示永不过期",
        "adapter": "dashscope",
        "endpoint": "https://dashscope.aliyuncs.com/api/v1/services/audio/tts/SpeechSynthesizer",
        "model": "cosyvoice-v1",
        "voice": "longyuan",
        "extra": {
            "format": "mp3",
            "sample_rate": 22050,
            "rate": 1.0,
            "free_limit_chars": 10000,
            "free_used_chars": 300,
            "free_remaining_chars": 9700,
            "free_expires_at": None,
            "allow_overage": False,
        },
    },
    "cosyvoice_clone": {
        "label": "CosyVoice 克隆音色",
        "free_quota": "10K chars",
        "quota_note": "截图显示永不过期",
        "adapter": "dashscope",
        "endpoint": "https://dashscope.aliyuncs.com/api/v1/services/audio/tts/SpeechSynthesizer",
        "model": "cosyvoice-clone-v1",
        "voice": "",
        "extra": {
            "format": "mp3",
            "sample_rate": 22050,
            "rate": 1.0,
            "free_limit_chars": 10000,
            "free_used_chars": 0,
            "free_remaining_chars": 10000,
            "free_expires_at": None,
            "allow_overage": False,
        },
    },
    "minimax": {
        "label": "MiniMax / TokenHub",
        "adapter": "minimax",
        "endpoint": "https://api.minimax.cn/v1/t2a_v2",
        "model": "speech-2.8-turbo",
        "voice": "female-tianmei",
        "extra": {"groupId": ""},
    },
    "volc": {
        "label": "豆包旧版 V1（AppID）",
        "free_quota": "5000 字符",
        "quota_note": "旧版接口，使用 AppID + Access Token",
        "adapter": "volc_v1",
        "endpoint": "https://openspeech.bytedance.com/api/v1/tts",
        "model": "",
        "voice": "BV700_streaming",
        "extra": {
            "appid": "",
            "cluster": "volcano_tts",
            "encoding": "mp3",
            "rate": 24000,
        },
    },
    "volc_tts1": {
        "label": "豆包语音合成 1.0（共享 Key）",
        "free_quota": "5000 字符",
        "quota_note": "与 TTS 2.0 / 声音复刻 2.0 共用独立豆包语音 Key",
        "secret_scope_label": "豆包语音共享 Key",
        "adapter": "volc_http_v3",
        "endpoint": "https://openspeech.bytedance.com/api/v3/tts/unidirectional",
        "model": "seed-tts-1.0",
        "voice": "zh_female_meilinvyou_moon_bigtts",
        "extra": {
            "resource_id": "seed-tts-1.0",
            "format": "mp3",
            "sample_rate": 24000,
            "free_limit_chars": 5000,
            "free_used_chars": 0,
            "free_remaining_chars": 5000,
            "free_expires_at": None,
            "allow_overage": False,
        },
    },
    "volc_agent": {
        "label": "火山 Agent Plan（独立 Key）",
        "free_quota": "套餐 AFP",
        "quota_note": "TTS 不看周限额；截图月剩 3 万 AFP",
        "secret_scope_label": "Agent Plan 独立 Key",
        "adapter": "volc_agent_http",
        "endpoint": "https://openspeech.bytedance.com/api/v3/plan/tts/unidirectional",
        "model": "doubao-seed-tts-2.0",
        "voice": "zh_female_vv_uranus_bigtts",
        "extra": {
            "resource_id": "seed-tts-2.0",
            "format": "mp3",
            "sample_rate": 24000,
            "afp_per_10k_chars": 1350,
            "afp_weekly_limit": 35000,
            "afp_weekly_remaining": 112,
            "afp_week_reset_at": "2026-09-14T00:00:00+08:00",
            "enforce_weekly_limit": False,
            "count_against_weekly": False,
            "afp_monthly_limit": 100000,
            "afp_monthly_remaining": 30000,
            "afp_month_reset_at": "2026-10-05T00:00:00+08:00",
            "allow_overage": False,
        },
    },
    "volc_tts2": {
        "label": "豆包语音合成 2.0（共享 Key）",
        "free_quota": "20000 字符",
        "quota_note": "与 TTS 1.0 / 声音复刻 2.0 共用独立豆包语音 Key",
        "secret_scope_label": "豆包语音共享 Key",
        "adapter": "volc_http_v3",
        "endpoint": "https://openspeech.bytedance.com/api/v3/tts/unidirectional",
        "model": "doubao-seed-tts-2.0",
        "voice": "zh_female_vv_uranus_bigtts",
        "extra": {
            "resource_id": "seed-tts-2.0",
            "format": "mp3",
            "sample_rate": 24000,
            "free_limit_chars": 20000,
            "free_used_chars": 0,
            "free_remaining_chars": 20000,
            "free_expires_at": None,
            "allow_overage": False,
        },
    },
    "volc_icl2": {
        "label": "豆包声音复刻 2.0（共享 Key）",
        "free_quota": "5000 字符",
        "quota_note": "与 TTS 1.0 / 2.0 共用 Key，需填写克隆音色 ID",
        "secret_scope_label": "豆包语音共享 Key",
        "adapter": "volc_http_v3",
        "endpoint": "https://openspeech.bytedance.com/api/v3/tts/unidirectional",
        "model": "doubao-seed-icl-2.0",
        "voice": "",
        "extra": {
            "resource_id": "seed-icl-2.0",
            "format": "mp3",
            "sample_rate": 24000,
            "free_limit_chars": 5000,
            "free_used_chars": 0,
            "free_remaining_chars": 5000,
            "free_expires_at": None,
            "allow_overage": False,
        },
    },
    "volc_design": {
        "label": "豆包音色设计（共享 Key）",
        "free_quota": "20000 字符",
        "quota_note": "设计接口，不直接输出成品音频",
        "secret_scope_label": "豆包语音共享 Key",
        "adapter": "manual",
        "endpoint": "https://openspeech.bytedance.com/api/v3/tts/voice_design",
        "model": "",
        "voice": "",
        "extra": {
            "free_limit_chars": 20000,
            "free_used_chars": 0,
            "free_remaining_chars": 20000,
            "free_expires_at": None,
            "allow_overage": False,
        },
    },
    "volc_audio1": {
        "label": "豆包音频生成 1.0（共享 Key）",
        "free_quota": "60 分钟",
        "quota_note": "支持参考音频，与豆包语音共享 Key",
        "secret_scope_label": "豆包语音共享 Key",
        "adapter": "volc_audio_http",
        "endpoint": "https://openspeech.bytedance.com/api/v3/tts/create",
        "model": "seed-audio-1.0",
        "voice": "zh_female_gaolengyujie_uranus_bigtts",
        "extra": {
            "format": "mp3",
            "sample_rate": 44100,
            "speech_rate": 0,
            "pitch_rate": 0,
            "reference_audio_path": "",
            "free_limit_seconds": 3600,
            "free_used_seconds": 0,
            "free_remaining_seconds": 3600,
            "allow_overage": False,
        },
    },
    "mimo_tts": {
        "label": "MiMo-V2.5-TTS",
        "free_quota": "限时免费",
        "quota_note": "官方按量计费页标注「限时免费」（2026-09-24 核实），未设本地字符闸门",
        "secret_scope_label": "MiMo API Key（三模型共用）",
        "adapter": "mimo_tts",
        "endpoint": "https://api.xiaomimimo.com/v1/chat/completions",
        "model": "mimo-v2.5-tts",
        "voice": "白桦",
        "extra": {
            "format": "wav",
            "style_prompt": "",
        },
    },
    "mimo_tts_clone": {
        "label": "MiMo-V2.5-TTS-VoiceClone",
        "free_quota": "限时免费",
        "quota_note": "官方按量计费页标注「限时免费」（2026-09-24 核实），未设本地字符闸门",
        "secret_scope_label": "MiMo API Key（三模型共用）",
        "adapter": "mimo_tts",
        "endpoint": "https://api.xiaomimimo.com/v1/chat/completions",
        "model": "mimo-v2.5-tts-voiceclone",
        "voice": "",
        "extra": {
            "format": "wav",
            "style_prompt": "",
            "reference_audio_path": "voices/podcast-voice.wav",
        },
    },
    "mimo_tts_design": {
        "label": "MiMo-V2.5-TTS-VoiceDesign",
        "free_quota": "限时免费",
        "quota_note": "官方按量计费页标注「限时免费」（2026-09-24 核实），未设本地字符闸门",
        "secret_scope_label": "MiMo API Key（三模型共用）",
        "adapter": "mimo_tts",
        "endpoint": "https://api.xiaomimimo.com/v1/chat/completions",
        "model": "mimo-v2.5-tts-voicedesign",
        "voice": "",
        "extra": {
            "format": "wav",
            "style_prompt": "沉稳温和的中文男声，语速适中，像深夜电台主持人",
            "optimize_text_preview": False,
        },
    },
    "custom": {
        "label": "自定义 OpenAI",
        "adapter": "openai",
        "endpoint": "",
        "model": "",
        "voice": "",
        "extra": {},
    },
}

VOLC_STANDALONE_PROVIDERS = {
    "volc_tts1",
    "volc_tts2",
    "volc_icl2",
    "volc_design",
    "volc_audio1",
}
VOLC_STANDALONE_KEY_ACCOUNT = "volc_doubao_voice_shared"

# 三个 MiMo TTS 模型共用同一个 API Key，Keychain 只存一份。
MIMO_PROVIDERS = {
    "mimo_tts",
    "mimo_tts_clone",
    "mimo_tts_design",
}
MIMO_KEY_ACCOUNT = "mimo_api"

class CloudTTSError(RuntimeError):
    pass


def config_dir() -> Path:
    return Path(os.environ.get("TTS_CONSOLE_CONFIG_DIR", DEFAULT_CONFIG_DIR))


def config_path() -> Path:
    return config_dir() / "config.json"


def load_config() -> dict[str, dict[str, Any]]:
    path = config_path()
    if not path.exists():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:
        raise CloudTTSError(f"配置文件损坏: {path}") from exc
    if not isinstance(data, dict):
        raise CloudTTSError(f"配置文件格式错误: {path}")
    return data


def save_config(data: dict[str, dict[str, Any]]) -> None:
    path = config_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    tmp.write_text(
        json.dumps(data, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    os.chmod(tmp, 0o600)
    tmp.replace(path)


def load_custom_providers() -> dict[str, dict[str, Any]]:
    """读取自定义 provider 段（config.json 的 ``_custom_providers``）。

    集中收口自定义 provider 的读写，确保它不会被当成一个普通 provider，
    也不会因为别的写路径 load→modify→save 而丢失。
    """
    raw = load_config().get(CUSTOM_PROVIDERS_KEY)
    if not isinstance(raw, dict):
        return {}
    out: dict[str, dict[str, Any]] = {}
    for pid, item in raw.items():
        if isinstance(item, dict):
            out[str(pid)] = copy.deepcopy(item)
    return out


def save_custom_providers(providers: dict[str, dict[str, Any]]) -> None:
    """写回整个自定义 provider 段，保留 config.json 里其它 provider 的配置。

    没有自定义 provider 时移除该段，避免在用户既有配置里留下空壳。
    """
    cleaned: dict[str, dict[str, Any]] = {}
    for pid, item in providers.items():
        if not isinstance(item, dict):
            continue
        entry = copy.deepcopy(item)
        extra = entry.get("extra")
        entry["extra"] = dict(extra) if isinstance(extra, dict) else {}
        cleaned[str(pid)] = entry
    data = load_config()
    if cleaned:
        data[CUSTOM_PROVIDERS_KEY] = cleaned
    else:
        data.pop(CUSTOM_PROVIDERS_KEY, None)
    save_config(data)


def is_custom_provider(provider: str) -> bool:
    return provider in load_custom_providers()


def provider_defaults(provider: str) -> dict[str, Any]:
    if provider in PROVIDER_PRESETS:
        return copy.deepcopy(PROVIDER_PRESETS[provider])
    custom = load_custom_providers().get(provider)
    if custom is not None:
        return copy.deepcopy(custom)
    raise CloudTTSError(f"未知 provider: {provider}")


def _apply_provider_migrations(
    provider: str,
    merged: dict[str, Any],
    defaults: dict[str, Any],
) -> None:
    if provider == "volc_agent":
        endpoint = str(merged.get("endpoint") or "")
        if merged.get("adapter") == "manual" or endpoint.startswith("wss://"):
            merged["adapter"] = defaults["adapter"]
            merged["endpoint"] = defaults["endpoint"]
        if not merged.get("voice"):
            merged["voice"] = defaults["voice"]


def get_provider_config(provider: str) -> dict[str, Any]:
    defaults = provider_defaults(provider)
    merged = copy.deepcopy(defaults)
    saved = load_config().get(provider, {})
    default_extra = dict(merged.get("extra") or {})
    merged.update(saved)
    merged["extra"] = {**default_extra, **dict(saved.get("extra") or {})}
    _apply_provider_migrations(provider, merged, defaults)
    return merged


def _has_secrets(providers: list[str]) -> dict[str, bool]:
    """并行探测一批 provider 是否已在 Keychain 里存了 Key。

    Keychain 查询要 fork ``security`` 子进程，串行跑十几个 provider 会明显拖慢
    一次 GET；这里并发一下，把整体墙钟时间压到「最慢的单个 provider」量级。
    """
    if not providers:
        return {}
    if len(providers) == 1:
        provider = providers[0]
        return {provider: has_provider_secret(provider)}
    out: dict[str, bool] = {}
    workers = min(12, len(providers))
    with concurrent.futures.ThreadPoolExecutor(max_workers=workers) as pool:
        futures = {pool.submit(has_provider_secret, p): p for p in providers}
        for future in concurrent.futures.as_completed(futures):
            provider = futures[future]
            try:
                out[provider] = bool(future.result())
            except Exception:  # noqa: BLE001 - 单个探测失败不拖垮整体
                out[provider] = False
    return out


def list_public_config() -> dict[str, dict[str, Any]]:
    saved = load_config()
    custom = load_custom_providers()
    all_providers: dict[str, dict[str, Any]] = {
        provider: copy.deepcopy(defaults)
        for provider, defaults in PROVIDER_PRESETS.items()
    }
    for pid, item in custom.items():
        if pid not in all_providers:
            all_providers[pid] = copy.deepcopy(item)

    secrets = _has_secrets(list(all_providers))

    out: dict[str, dict[str, Any]] = {}
    for provider, defaults in all_providers.items():
        item = copy.deepcopy(defaults)
        default_extra = dict(item.get("extra") or {})
        saved_entry = saved.get(provider)
        if isinstance(saved_entry, dict):
            item.update(saved_entry)
            item["extra"] = {
                **default_extra,
                **dict(saved_entry.get("extra") or {}),
            }
        else:
            item["extra"] = default_extra
        _apply_provider_migrations(provider, item, defaults)
        item["provider"] = provider
        item["custom"] = provider not in PROVIDER_PRESETS
        item["has_secret"] = secrets.get(provider, False)
        out[provider] = item
    return out


def _validate_extra(extra: dict[str, Any]) -> None:
    forbidden = re.compile(
        r"(api[_-]?key|access[_-]?token|token|secret|authorization)", re.I
    )
    for key in extra:
        if forbidden.search(str(key)):
            raise CloudTTSError(
                f"额外参数里不要放密钥字段: {key}。密钥只从 Keychain 读取。"
            )


def _validate_adapter_endpoint(adapter: str, endpoint: str) -> str:
    """校验 adapter 与 endpoint，返回 strip 后的 endpoint。"""
    if adapter not in ALLOWED_ADAPTERS:
        raise CloudTTSError(f"不支持的 adapter: {adapter}")
    endpoint = endpoint.strip()
    parsed = urllib.parse.urlparse(endpoint)
    allowed_schemes = (
        ("http", "https", "ws", "wss") if adapter == "manual" else ("http", "https")
    )
    if parsed.scheme not in allowed_schemes or not parsed.netloc:
        expected = "http/https/ws/wss" if adapter == "manual" else "http/https"
        raise CloudTTSError(f"endpoint 必须是完整 {expected} 地址")
    for key in urllib.parse.parse_qs(parsed.query):
        if re.search(r"(key|token|secret|authorization)", key, re.I):
            raise CloudTTSError("endpoint 查询参数里不要放密钥，密钥只从 Keychain 读取")
    return endpoint


def update_provider_config(
    provider: str,
    *,
    adapter: str,
    endpoint: str,
    model: str,
    voice: str,
    extra: dict[str, Any],
    secret: str | None,
    clear_secret: bool = False,
    label: str | None = None,
) -> None:
    is_preset = provider in PROVIDER_PRESETS
    custom = load_custom_providers()
    is_custom = provider in custom
    if not is_preset and not is_custom:
        raise CloudTTSError(f"未知 provider: {provider}")

    endpoint = _validate_adapter_endpoint(adapter, endpoint)
    _validate_extra(extra)

    existing = get_provider_config(provider)
    merged = {
        "adapter": adapter,
        "endpoint": endpoint,
        "model": model.strip(),
        "voice": voice.strip(),
        "extra": {**dict(existing.get("extra") or {}), **extra},
    }

    if is_custom:
        entry = dict(custom.get(provider) or {})
        entry.update(merged)
        if label is not None and str(label).strip():
            entry["label"] = str(label).strip()
        entry.setdefault("label", provider)
        custom[provider] = entry
        save_custom_providers(custom)
    else:
        data = load_config()
        data[provider] = merged
        save_config(data)

    if clear_secret:
        delete_keychain_secret(provider)
    elif secret:
        set_keychain_secret(provider, secret)


def create_custom_provider(
    provider_id: str,
    label: str,
    adapter: str,
    endpoint: str,
    model: str,
    voice: str,
    extra: dict[str, Any] | None = None,
) -> str:
    """新增一个自定义 provider，返回规范化后的 id。

    只写 config.json 的非敏感段；Key 由调用方另行写入 Keychain。
    """
    pid = str(provider_id or "").strip().lower()
    if not _PROVIDER_ID_RE.fullmatch(pid):
        raise CloudTTSError(
            "id 只能用小写字母、数字、- 和 _，2-40 位，且以字母或数字开头"
        )
    if pid in PROVIDER_PRESETS:
        raise CloudTTSError(f"id 和预设冲突，换一个：{pid}")
    custom = load_custom_providers()
    if pid in custom:
        raise CloudTTSError(f"自定义 id 已存在：{pid}")

    endpoint = _validate_adapter_endpoint(adapter, endpoint or "")
    extra = dict(extra or {})
    _validate_extra(extra)

    custom[pid] = {
        "label": str(label or "").strip() or pid,
        "adapter": adapter,
        "endpoint": endpoint,
        "model": str(model or "").strip(),
        "voice": str(voice or "").strip(),
        "extra": extra,
    }
    save_custom_providers(custom)
    return pid


def delete_custom_provider(provider_id: str) -> None:
    """删除一个自定义 provider，连带清掉它的 Keychain secret。

    预设 provider 一律拒绝删除。
    """
    pid = str(provider_id or "").strip().lower()
    if pid in PROVIDER_PRESETS:
        raise CloudTTSError("预设 provider 不能删除")
    custom = load_custom_providers()
    if pid not in custom:
        raise CloudTTSError(f"自定义 provider 不存在：{pid}")

    custom.pop(pid, None)
    save_custom_providers(custom)
    delete_keychain_secret(pid)

    # 清掉可能残留的同名顶层覆盖段，避免删不干净。
    data = load_config()
    if pid in data and pid != CUSTOM_PROVIDERS_KEY:
        data.pop(pid, None)
        save_config(data)


def list_adapters() -> list[dict[str, str]]:
    """协议适配器清单（含人话说明），供前端选择时参考。"""
    return [dict(item) for item in ADAPTER_INFO]


def _run_security(args: list[str], *, check: bool = True) -> subprocess.CompletedProcess:
    if shutil.which("security") is None:
        raise CloudTTSError("找不到 macOS security 命令，无法使用 Keychain")
    proc = subprocess.run(args, capture_output=True, text=True)
    if check and proc.returncode != 0:
        detail = (proc.stderr or proc.stdout).strip()
        raise CloudTTSError(f"Keychain 操作失败: {detail}")
    return proc


def set_keychain_secret(provider: str, secret: str) -> None:
    if not secret:
        return
    if "\n" in secret or "\r" in secret:
        raise CloudTTSError("API Key 不能包含换行")
    encoded = "b64:" + base64.b64encode(secret.encode("utf-8")).decode("ascii")
    if shutil.which("security") is None:
        raise CloudTTSError("找不到 macOS security 命令，无法使用 Keychain")
    if provider in VOLC_STANDALONE_PROVIDERS:
        account = VOLC_STANDALONE_KEY_ACCOUNT
    elif provider in MIMO_PROVIDERS:
        account = MIMO_KEY_ACCOUNT
    else:
        account = provider
    command = (
        "add-generic-password -U "
        f"-a {account} -s {KEYCHAIN_SERVICE} -w {encoded}\n"
    )
    proc = subprocess.run(
        ["security", "-i"],
        input=command,
        capture_output=True,
        text=True,
    )
    if proc.returncode != 0:
        detail = (proc.stderr or proc.stdout).strip()
        raise CloudTTSError(f"Keychain 操作失败: {detail}")


def get_keychain_secret(provider: str) -> str:
    if provider in VOLC_STANDALONE_PROVIDERS:
        account = VOLC_STANDALONE_KEY_ACCOUNT
    elif provider in MIMO_PROVIDERS:
        account = MIMO_KEY_ACCOUNT
    else:
        account = provider
    proc = _run_security(
        [
            "security",
            "find-generic-password",
            "-a",
            account,
            "-s",
            KEYCHAIN_SERVICE,
            "-w",
        ],
        check=False,
    )
    if proc.returncode != 0:
        if provider in VOLC_STANDALONE_PROVIDERS:
            for legacy_provider in sorted(VOLC_STANDALONE_PROVIDERS):
                legacy = _run_security(
                    [
                        "security",
                        "find-generic-password",
                        "-a",
                        legacy_provider,
                        "-s",
                        KEYCHAIN_SERVICE,
                        "-w",
                    ],
                    check=False,
                )
                if legacy.returncode == 0:
                    return _decode_secret(legacy.stdout.rstrip("\n"))
        return ""
    return _decode_secret(proc.stdout.rstrip("\n"))


def _decode_secret(value: str) -> str:
    if value.startswith("b64:"):
        try:
            return base64.b64decode(value[4:]).decode("utf-8")
        except Exception as exc:
            raise CloudTTSError("Keychain 中的 Key 编码损坏") from exc
    return value


def has_keychain_secret(provider: str) -> bool:
    return bool(get_keychain_secret(provider))


def get_provider_secret(provider: str) -> str:
    return get_keychain_secret(provider)


def has_provider_secret(provider: str) -> bool:
    return bool(get_provider_secret(provider))


def delete_keychain_secret(provider: str) -> None:
    accounts = [provider]
    if provider in VOLC_STANDALONE_PROVIDERS:
        accounts.append(VOLC_STANDALONE_KEY_ACCOUNT)
        accounts.extend(sorted(VOLC_STANDALONE_PROVIDERS))
    if provider in MIMO_PROVIDERS:
        accounts.append(MIMO_KEY_ACCOUNT)
        accounts.extend(sorted(MIMO_PROVIDERS))
    for account in dict.fromkeys(accounts):
        _run_security(
            [
                "security",
                "delete-generic-password",
                "-a",
                account,
                "-s",
                KEYCHAIN_SERVICE,
            ],
            check=False,
        )


def _opener() -> urllib.request.OpenerDirector:
    # 项目 shell 环境常带失效的 127.0.0.1:7890 代理，这里显式直连。
    return urllib.request.build_opener(urllib.request.ProxyHandler({}))


def _request_json(
    url: str,
    *,
    payload: dict[str, Any],
    headers: dict[str, str],
    timeout: int = 180,
) -> dict[str, Any]:
    body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    req = urllib.request.Request(
        url,
        data=body,
        headers={"Content-Type": "application/json", **headers},
        method="POST",
    )
    try:
        with _opener().open(req, timeout=timeout) as resp:
            raw = resp.read()
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        raise CloudTTSError(f"HTTP {exc.code}: {detail[:1000]}") from exc
    except urllib.error.URLError as exc:
        raise CloudTTSError(f"请求失败: {exc.reason}") from exc
    try:
        return json.loads(raw.decode("utf-8"))
    except Exception as exc:
        raise CloudTTSError(f"响应不是 JSON: {raw[:200]!r}") from exc


def _download(url: str, timeout: int = 180) -> tuple[bytes, str]:
    req = urllib.request.Request(url, headers={"User-Agent": "tts-console/1.0"})
    try:
        with _opener().open(req, timeout=timeout) as resp:
            return resp.read(), resp.headers.get_content_type()
    except urllib.error.URLError as exc:
        raise CloudTTSError(f"下载音频失败: {exc.reason}") from exc


def _extension_from_content_type(content_type: str, fallback: str) -> str:
    mapping = {
        "audio/mpeg": "mp3",
        "audio/mp3": "mp3",
        "audio/wav": "wav",
        "audio/x-wav": "wav",
        "audio/ogg": "ogg",
        "audio/opus": "opus",
    }
    return mapping.get(content_type, fallback)


def _synthesize_dashscope(
    cfg: dict[str, Any],
    text: str,
    secret: str,
) -> tuple[str, bytes]:
    extra = cfg.get("extra") or {}
    payload = {
        "model": cfg.get("model") or "qwen3-tts-flash",
        "input": {
            "text": text,
            "voice": cfg.get("voice") or "Cherry",
        },
    }
    if extra.get("language_type"):
        payload["input"]["language_type"] = extra["language_type"]
    if extra.get("instructions"):
        payload["input"]["instructions"] = extra["instructions"]
    if extra.get("optimize_instructions") is not None:
        payload["input"]["optimize_instructions"] = bool(
            extra["optimize_instructions"]
        )
    for key in ("format", "sample_rate", "rate", "volume", "pitch"):
        if extra.get(key) is not None:
            payload["input"][key] = extra[key]
    data = _request_json(
        cfg["endpoint"],
        payload=payload,
        headers={"Authorization": f"Bearer {secret}"},
    )
    audio = (data.get("output") or {}).get("audio") or {}
    if audio.get("data"):
        return "wav", base64.b64decode(audio["data"])
    if audio.get("url"):
        raw, content_type = _download(audio["url"])
        return _extension_from_content_type(content_type, "wav"), raw
    raise CloudTTSError(f"DashScope 未返回音频: {json.dumps(data, ensure_ascii=False)[:1000]}")


def _synthesize_dashscope_sdk(
    cfg: dict[str, Any],
    text: str,
    secret: str,
) -> tuple[str, bytes]:
    try:
        import dashscope
        from dashscope.audio.tts_v2 import AudioFormat, SpeechSynthesizer
    except ImportError as exc:
        raise CloudTTSError(
            "CosyVoice v1 需要 DashScope SDK，请用 "
            "~/.local/share/ai-jarvis/tts-console/venv/bin/python 运行"
        ) from exc

    extra = cfg.get("extra") or {}
    dashscope.api_key = secret
    dashscope.base_websocket_api_url = (
        "wss://dashscope.aliyuncs.com/api-ws/v1/inference"
    )
    audio_format = AudioFormat.MP3_22050HZ_MONO_256KBPS
    fmt = str(extra.get("format") or "mp3").lower()
    sample_rate = int(extra.get("sample_rate") or 22050)
    if fmt == "wav":
        audio_format = {
            16000: AudioFormat.WAV_16000HZ_MONO_16BIT,
            22050: AudioFormat.WAV_22050HZ_MONO_16BIT,
            24000: AudioFormat.WAV_24000HZ_MONO_16BIT,
            44100: AudioFormat.WAV_44100HZ_MONO_16BIT,
            48000: AudioFormat.WAV_48000HZ_MONO_16BIT,
        }.get(sample_rate, AudioFormat.WAV_22050HZ_MONO_16BIT)
    elif fmt == "pcm":
        audio_format = {
            16000: AudioFormat.PCM_16000HZ_MONO_16BIT,
            22050: AudioFormat.PCM_22050HZ_MONO_16BIT,
            24000: AudioFormat.PCM_24000HZ_MONO_16BIT,
            44100: AudioFormat.PCM_44100HZ_MONO_16BIT,
            48000: AudioFormat.PCM_48000HZ_MONO_16BIT,
        }.get(sample_rate, AudioFormat.PCM_22050HZ_MONO_16BIT)
    synthesizer = SpeechSynthesizer(
        model=cfg.get("model") or "cosyvoice-v1",
        voice=cfg.get("voice") or "longyuan",
        format=audio_format,
        volume=int(extra.get("volume") or 50),
        speech_rate=float(extra.get("rate") or extra.get("speech_rate") or 1),
        pitch_rate=float(extra.get("pitch") or extra.get("pitch_rate") or 1),
    )
    audio = synthesizer.call(text)
    if not audio:
        response = synthesizer.get_response()
        raise CloudTTSError(
            f"CosyVoice 未返回音频: {json.dumps(response, ensure_ascii=False)[:1000]}"
        )
    return fmt if fmt in ("mp3", "wav", "pcm") else "mp3", audio


def _synthesize_minimax(
    cfg: dict[str, Any],
    text: str,
    secret: str,
) -> tuple[str, bytes]:
    extra = cfg.get("extra") or {}
    endpoint = cfg["endpoint"]
    group_id = str(extra.get("groupId") or "").strip()
    if group_id and "GroupId=" not in endpoint:
        joiner = "&" if "?" in endpoint else "?"
        endpoint = f"{endpoint}{joiner}GroupId={urllib.parse.quote(group_id)}"
    audio_format = str(extra.get("format") or "mp3")
    payload = {
        "model": cfg.get("model") or "speech-2.8-turbo",
        "text": text,
        "stream": False,
        "voice_setting": {
            "voice_id": cfg.get("voice") or "female-tianmei",
            "speed": float(extra.get("speed") or 1),
            "vol": float(extra.get("vol") or 1),
            "pitch": float(extra.get("pitch") or 0),
        },
        "audio_setting": {
            "sample_rate": int(extra.get("sample_rate") or 32000),
            "bitrate": int(extra.get("bitrate") or 128000),
            "format": audio_format,
            "channel": int(extra.get("channel") or 1),
        },
    }
    if extra.get("emotion"):
        payload["voice_setting"]["emotion"] = extra["emotion"]
    data = _request_json(
        endpoint,
        payload=payload,
        headers={"Authorization": f"Bearer {secret}"},
    )
    audio_value = ((data.get("data") or {}).get("audio") or "").strip()
    if not audio_value:
        raise CloudTTSError(
            f"MiniMax 未返回音频: {json.dumps(data, ensure_ascii=False)[:1000]}"
        )
    if audio_value.startswith(("http://", "https://")):
        raw, content_type = _download(audio_value)
        return _extension_from_content_type(content_type, audio_format), raw
    try:
        return audio_format, bytes.fromhex(audio_value)
    except ValueError as exc:
        raise CloudTTSError("MiniMax 返回的 audio 既不是 URL 也不是 hex") from exc


def _synthesize_volc_v1(
    cfg: dict[str, Any],
    text: str,
    secret: str,
) -> tuple[str, bytes]:
    extra = cfg.get("extra") or {}
    appid = str(extra.get("appid") or "").strip()
    cluster = str(extra.get("cluster") or "").strip()
    if not appid or not cluster:
        raise CloudTTSError("火山 V1 需要额外参数 appid 和 cluster")
    encoding = str(extra.get("encoding") or "mp3")
    payload = {
        "app": {
            "appid": appid,
            "token": secret,
            "cluster": cluster,
        },
        "user": {"uid": str(extra.get("uid") or "tts-console")},
        "audio": {
            "voice_type": cfg.get("voice") or "BV700_streaming",
            "encoding": encoding,
            "rate": int(extra.get("rate") or 24000),
            "speed_ratio": float(extra.get("speed_ratio") or 1),
            "volume_ratio": float(extra.get("volume_ratio") or 1),
            "pitch_ratio": float(extra.get("pitch_ratio") or 1),
        },
        "request": {
            "reqid": str(uuid.uuid4()),
            "text": text,
            "text_type": "plain",
            "operation": "query",
        },
    }
    data = _request_json(
        cfg["endpoint"],
        payload=payload,
        headers={"Authorization": f"Bearer; {secret}"},
    )
    if data.get("code") not in (3000, "3000", None):
        raise CloudTTSError(
            f"火山 V1 返回错误: {json.dumps(data, ensure_ascii=False)[:1000]}"
        )
    audio_b64 = data.get("data")
    if not audio_b64:
        raise CloudTTSError(f"火山 V1 未返回音频: {json.dumps(data, ensure_ascii=False)[:1000]}")
    return encoding, base64.b64decode(audio_b64)


def _parse_iso(value: str) -> dt.datetime | None:
    if not value:
        return None
    try:
        parsed = dt.datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=dt.timezone.utc)
    return parsed


def _volc_agent_quota(text: str, extra: dict[str, Any]) -> tuple[int, int, int]:
    chars = len(text)
    coefficient = float(extra.get("afp_per_10k_chars") or 1350)
    cost = max(1, math.ceil(chars / 10000 * coefficient))
    now = dt.datetime.now().astimezone()
    weekly_limit = int(extra.get("afp_weekly_limit") or 35000)
    monthly_limit = int(extra.get("afp_monthly_limit") or 100000)
    weekly_remaining = int(extra.get("afp_weekly_remaining") or 0)
    monthly_remaining = int(extra.get("afp_monthly_remaining") or 0)
    week_reset = _parse_iso(str(extra.get("afp_week_reset_at") or ""))
    month_reset = _parse_iso(str(extra.get("afp_month_reset_at") or ""))
    if week_reset and now >= week_reset:
        weekly_remaining = weekly_limit
    if month_reset and now >= month_reset:
        monthly_remaining = monthly_limit
    if not bool(extra.get("allow_overage")):
        if bool(extra.get("enforce_weekly_limit")) and cost > weekly_remaining:
            raise CloudTTSError(
                f"AFP 周额度不足：本次约需 {cost} AFP，当前剩余 {weekly_remaining} AFP。"
                "周额度重置或更新配置后再调用。"
            )
        if cost > monthly_remaining:
            raise CloudTTSError(
                f"AFP 月额度不足：本次约需 {cost} AFP，当前剩余 {monthly_remaining} AFP。"
                "月额度重置或更新配置后再调用。"
            )
    return cost, weekly_remaining, monthly_remaining


def _synthesize_volc_agent_http(
    cfg: dict[str, Any],
    text: str,
    secret: str,
) -> tuple[str, bytes]:
    extra = cfg.get("extra") or {}
    if extra.get("afp_per_10k_chars") is not None:
        _volc_agent_quota(text, extra)
    audio_format = str(extra.get("format") or "mp3")
    payload = {
        "req_params": {
            "text": text,
            "speaker": cfg.get("voice") or "zh_female_vv_uranus_bigtts",
            "audio_params": {
                "format": audio_format,
                "sample_rate": int(extra.get("sample_rate") or 24000),
            },
        }
    }
    body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    req = urllib.request.Request(
        cfg["endpoint"],
        data=body,
        headers={
            "Content-Type": "application/json",
            "X-Api-Key": secret,
            "X-Api-Resource-Id": str(extra.get("resource_id") or "seed-tts-2.0"),
            "X-Control-Require-Usage-Tokens-Return": "*",
            "Connection": "keep-alive",
        },
        method="POST",
    )
    chunks = bytearray()
    try:
        with _opener().open(req, timeout=300) as resp:
            for raw_line in resp:
                line = raw_line.decode("utf-8", errors="replace").strip()
                if not line:
                    continue
                if line.startswith("data:"):
                    line = line[5:].strip()
                try:
                    item = json.loads(line)
                except json.JSONDecodeError as exc:
                    raise CloudTTSError(f"火山 Agent Plan 返回非 JSON 行: {line[:300]}") from exc
                code = item.get("code", 0)
                if code == 0 and item.get("data"):
                    chunks.extend(base64.b64decode(item["data"]))
                elif code == 20000000:
                    break
                elif code:
                    raise CloudTTSError(
                        f"火山 Agent Plan 错误: {json.dumps(item, ensure_ascii=False)[:1000]}"
                    )
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        raise CloudTTSError(f"HTTP {exc.code}: {detail[:1000]}") from exc
    except urllib.error.URLError as exc:
        raise CloudTTSError(f"请求失败: {exc.reason}") from exc
    if not chunks:
        raise CloudTTSError("火山 Agent Plan 未返回音频")
    return audio_format, bytes(chunks)


def _record_volc_agent_usage(provider: str, cost: int) -> None:
    data = load_config()
    saved = data.setdefault(provider, {})
    extra = {
        **dict(provider_defaults(provider).get("extra") or {}),
        **dict(saved.get("extra") or {}),
    }
    if bool(extra.get("count_against_weekly")):
        extra["afp_weekly_remaining"] = max(
            0, int(extra.get("afp_weekly_remaining") or 0) - cost
        )
    extra["afp_monthly_remaining"] = max(
        0, int(extra.get("afp_monthly_remaining") or 0) - cost
    )
    saved["extra"] = extra
    save_config(data)


def _free_quota_cost(provider: str, cfg: dict[str, Any], text: str) -> int | None:
    extra = cfg.get("extra") or {}
    if extra.get("free_remaining_chars") is None:
        return None
    adapter = cfg.get("adapter")
    model = str(cfg.get("model") or "")
    if adapter == "dashscope" and model.startswith("qwen-audio"):
        han = sum("\u4e00" <= char <= "\u9fff" for char in text)
        return han * 2 + (len(text) - han)
    return len(text)


def _guard_free_quota(provider: str, cfg: dict[str, Any], text: str) -> None:
    cost = _free_quota_cost(provider, cfg, text)
    if cost is None:
        return
    extra = cfg.get("extra") or {}
    remaining = int(extra.get("free_remaining_chars") or 0)
    expiry = _parse_iso(str(extra.get("free_expires_at") or ""))
    if expiry and dt.datetime.now().astimezone() >= expiry:
        remaining = 0
    if not bool(extra.get("allow_overage")) and cost > remaining:
        raise CloudTTSError(
            f"{provider} 免费额度不足：本次预计 {cost} 字符，剩余 {remaining} 字符。"
            "已阻止调用，避免转后付费。"
        )


def _record_free_usage(provider: str, cost: int | None) -> None:
    if cost is None or cost <= 0:
        return
    data = load_config()
    defaults = provider_defaults(provider)
    saved = data.setdefault(provider, {})
    extra = {
        **dict(defaults.get("extra") or {}),
        **dict(saved.get("extra") or {}),
    }
    remaining = int(extra.get("free_remaining_chars") or 0)
    used = int(extra.get("free_used_chars") or 0)
    extra["free_remaining_chars"] = max(0, remaining - cost)
    extra["free_used_chars"] = used + cost
    saved["extra"] = extra
    save_config(data)


def _guard_audio_generation_seconds(provider: str, cfg: dict[str, Any]) -> None:
    extra = cfg.get("extra") or {}
    if extra.get("free_remaining_seconds") is None:
        return
    remaining = float(extra.get("free_remaining_seconds") or 0)
    safety_seconds = float(extra.get("quota_safety_seconds") or 120)
    if not bool(extra.get("allow_overage")) and remaining < safety_seconds:
        raise CloudTTSError(
            f"{provider} 音频生成免费额度不足：剩余 {remaining:.1f} 秒，"
            f"单次保护阈值 {safety_seconds:.0f} 秒。已阻止调用，避免转后付费。"
        )


def _record_audio_generation_usage(provider: str, seconds: float) -> None:
    if seconds <= 0:
        return
    data = load_config()
    defaults = provider_defaults(provider)
    saved = data.setdefault(provider, {})
    extra = {
        **dict(defaults.get("extra") or {}),
        **dict(saved.get("extra") or {}),
    }
    extra["free_remaining_seconds"] = max(
        0, float(extra.get("free_remaining_seconds") or 0) - seconds
    )
    extra["free_used_seconds"] = float(extra.get("free_used_seconds") or 0) + seconds
    saved["extra"] = extra
    save_config(data)


def _reference_audio_base64(raw_path: str) -> str:
    path = Path(raw_path)
    if not path.is_absolute():
        path = PROJECT_ROOT / path
    path = path.resolve()
    try:
        path.relative_to(PROJECT_ROOT)
    except ValueError as exc:
        raise CloudTTSError("参考音频只允许读取项目目录内文件") from exc
    if not path.is_file():
        raise CloudTTSError(f"参考音频不存在: {path}")
    return base64.b64encode(path.read_bytes()).decode("ascii")


def _synthesize_volc_audio1(
    cfg: dict[str, Any],
    text: str,
    secret: str,
) -> tuple[str, bytes]:
    extra = cfg.get("extra") or {}
    _guard_audio_generation_seconds("volc_audio1", cfg)
    audio_format = str(extra.get("format") or "mp3")
    payload: dict[str, Any] = {
        "model": cfg.get("model") or "seed-audio-1.0",
        "text_prompt": text,
        "audio_config": {
            "format": audio_format,
            "sample_rate": int(extra.get("sample_rate") or 44100),
            "speech_rate": int(extra.get("speech_rate") or 0),
            "loudness_rate": int(extra.get("loudness_rate") or 0),
            "pitch_rate": int(extra.get("pitch_rate") or 0),
        },
    }
    reference_path = str(extra.get("reference_audio_path") or "").strip()
    if reference_path:
        payload["audio_data"] = _reference_audio_base64(reference_path)
    else:
        payload["speaker"] = cfg.get("voice") or "zh_female_gaolengyujie_uranus_bigtts"
    data = _request_json(
        cfg["endpoint"],
        payload=payload,
        headers={
            "X-Api-Key": secret,
            "X-Api-Request-Id": str(uuid.uuid4()),
        },
        timeout=300,
    )
    if data.get("code") not in (0, "0", None):
        raise CloudTTSError(
            f"豆包音频生成错误: {json.dumps(data, ensure_ascii=False)[:1000]}"
        )
    cfg["_last_original_duration"] = float(
        data.get("original_duration") or data.get("duration") or 0
    )
    if data.get("audio"):
        try:
            return audio_format, base64.b64decode(data["audio"])
        except Exception as exc:
            raise CloudTTSError("豆包音频生成返回的 audio 不是合法 base64") from exc
    if data.get("url"):
        raw, content_type = _download(data["url"])
        return _extension_from_content_type(content_type, audio_format), raw
    raise CloudTTSError(
        f"豆包音频生成未返回音频: {json.dumps(data, ensure_ascii=False)[:1000]}"
    )


def _synthesize_openai(
    cfg: dict[str, Any],
    text: str,
    secret: str,
) -> tuple[str, bytes]:
    extra = cfg.get("extra") or {}
    response_format = str(extra.get("response_format") or "mp3")
    payload = {
        "model": cfg.get("model") or "",
        "input": text,
        "voice": cfg.get("voice") or "",
        "response_format": response_format,
    }
    if extra.get("speed") is not None:
        payload["speed"] = float(extra["speed"])
    body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    req = urllib.request.Request(
        cfg["endpoint"],
        data=body,
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {secret}",
        },
        method="POST",
    )
    try:
        with _opener().open(req, timeout=300) as resp:
            raw = resp.read()
            content_type = resp.headers.get_content_type()
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        raise CloudTTSError(f"HTTP {exc.code}: {detail[:1000]}") from exc
    except urllib.error.URLError as exc:
        raise CloudTTSError(f"请求失败: {exc.reason}") from exc
    if "json" in content_type:
        try:
            detail = raw.decode("utf-8", errors="replace")
        except Exception:
            detail = repr(raw[:500])
        raise CloudTTSError(f"服务返回 JSON 而不是音频: {detail[:1000]}")
    return _extension_from_content_type(content_type, response_format), raw


def _synthesize_mimo(
    cfg: dict[str, Any],
    text: str,
    secret: str,
) -> tuple[str, bytes]:
    """MiMo-V2.5-TTS 系列：chat.completions + audio 字段，base64 音频在
    ``choices[0].message.audio.data`` 里返回（不是 OpenAI /audio/speech 协议）。"""
    extra = cfg.get("extra") or {}
    model = str(cfg.get("model") or "mimo-v2.5-tts")
    audio_format = str(extra.get("format") or "wav")
    style = str(extra.get("style_prompt") or "").strip()

    # 目标文本必须在 role=assistant；user 消息放风格指令或音色描述。
    messages: list[dict[str, Any]] = []
    if model.endswith("-voicedesign"):
        if not style:
            raise CloudTTSError(
                "mimo-v2.5-tts-voicedesign 需要在 extra.style_prompt 里写音色描述"
            )
        messages.append({"role": "user", "content": style})
    else:
        # voiceclone 官方示例 user 为空串；预置音色模型 user 可省略，这里统一给一条。
        messages.append({"role": "user", "content": style})
    messages.append({"role": "assistant", "content": text})

    audio_field: dict[str, Any] = {"format": audio_format}
    if model.endswith("-voiceclone"):
        reference_path = str(extra.get("reference_audio_path") or "").strip()
        if not reference_path:
            raise CloudTTSError(
                "mimo-v2.5-tts-voiceclone 需要在 extra.reference_audio_path "
                "里填参考音频路径（项目目录内）"
            )
        raw_path = Path(reference_path)
        if not raw_path.is_absolute():
            raw_path = PROJECT_ROOT / raw_path
        raw_path = raw_path.resolve()
        try:
            raw_path.relative_to(PROJECT_ROOT)
        except ValueError as exc:
            raise CloudTTSError("参考音频只允许读取项目目录内文件") from exc
        if not raw_path.is_file():
            raise CloudTTSError(f"参考音频不存在: {raw_path}")
        suffix = raw_path.suffix.lower()
        mime = "audio/mpeg" if suffix == ".mp3" else "audio/wav"
        voice_b64 = base64.b64encode(raw_path.read_bytes()).decode("ascii")
        # voiceclone 的 voice 字段直接传参考音频 Data URL。
        audio_field["voice"] = f"data:{mime};base64,{voice_b64}"
    elif model.endswith("-voicedesign"):
        if bool(extra.get("optimize_text_preview")):
            audio_field["optimize_text_preview"] = True
    else:
        audio_field["voice"] = str(cfg.get("voice") or "mimo_default")

    payload = {
        "model": model,
        "messages": messages,
        "audio": audio_field,
    }
    data = _request_json(
        cfg["endpoint"],
        payload=payload,
        headers={"Authorization": f"Bearer {secret}"},
        timeout=300,
    )
    try:
        audio_b64 = data["choices"][0]["message"]["audio"]["data"]
        raw = base64.b64decode(audio_b64)
    except (KeyError, IndexError, TypeError) as exc:
        raise CloudTTSError(
            f"MiMo 未返回音频: {json.dumps(data, ensure_ascii=False)[:800]}"
        ) from exc
    except ValueError as exc:
        raise CloudTTSError("MiMo 返回的音频不是合法 base64") from exc
    ext = "wav" if audio_format in ("wav", "pcm16") else "mp3"
    return ext, raw


def synthesize(provider: str, text: str, output: Path | None = None) -> Path:
    text = text.strip()
    if not text:
        raise CloudTTSError("文本为空")
    cfg = get_provider_config(provider)
    secret = get_provider_secret(provider)
    if not secret:
        raise CloudTTSError(f"{provider} 还没有保存 API Key")
    _guard_free_quota(provider, cfg, text)
    free_cost = _free_quota_cost(provider, cfg, text)
    adapter = cfg.get("adapter")
    if adapter == "dashscope":
        model = str(cfg.get("model") or "")
        if model.startswith(("cosyvoice-v1", "cosyvoice-clone-v1")):
            ext, audio = _synthesize_dashscope_sdk(cfg, text, secret)
        else:
            ext, audio = _synthesize_dashscope(cfg, text, secret)
    elif adapter == "minimax":
        ext, audio = _synthesize_minimax(cfg, text, secret)
    elif adapter == "volc_v1":
        ext, audio = _synthesize_volc_v1(cfg, text, secret)
    elif adapter in ("volc_agent_http", "volc_http_v3"):
        ext, audio = _synthesize_volc_agent_http(cfg, text, secret)
    elif adapter == "volc_audio_http":
        ext, audio = _synthesize_volc_audio1(cfg, text, secret)
    elif adapter == "openai":
        ext, audio = _synthesize_openai(cfg, text, secret)
    elif adapter == "mimo_tts":
        ext, audio = _synthesize_mimo(cfg, text, secret)
    elif adapter == "manual":
        raise CloudTTSError(
            "该 provider 目前只保存配置；直接合成适配器尚未接入。"
        )
    else:
        raise CloudTTSError(f"不支持的 adapter: {adapter}")

    if output is None:
        out_dir = Path(os.environ.get("TTS_CONSOLE_OUTPUT_DIR", DEFAULT_OUTPUT_DIR))
        out_dir.mkdir(parents=True, exist_ok=True)
        stamp = time.strftime("%Y%m%d-%H%M%S")
        output = out_dir / f"{stamp}-{provider}.{ext}"
    else:
        output = output.expanduser().resolve()
        output.parent.mkdir(parents=True, exist_ok=True)
    output.write_bytes(audio)
    if free_cost is not None:
        _record_free_usage(provider, free_cost)
    if adapter in ("volc_agent_http", "volc_http_v3") and (
        cfg.get("extra") or {}
    ).get("afp_per_10k_chars") is not None:
        cost, _, _ = _volc_agent_quota(text, cfg.get("extra") or {})
        _record_volc_agent_usage(provider, cost)
    if adapter == "volc_audio_http":
        _record_audio_generation_usage(
            provider, float(cfg.get("_last_original_duration") or 0)
        )
    return output


def _cmd_list(_: argparse.Namespace) -> int:
    print(json.dumps(list_public_config(), ensure_ascii=False, indent=2))
    return 0


def _cmd_show(args: argparse.Namespace) -> int:
    cfg = get_provider_config(args.provider)
    cfg["has_secret"] = has_provider_secret(args.provider)
    print(json.dumps(cfg, ensure_ascii=False, indent=2))
    return 0


def _cmd_set_secret(args: argparse.Namespace) -> int:
    set_keychain_secret(args.provider, args.secret)
    print(f"已保存 {args.provider} 的 Key 到 macOS Keychain")
    return 0


def _cmd_delete_secret(args: argparse.Namespace) -> int:
    delete_keychain_secret(args.provider)
    print(f"已删除 {args.provider} 的 Key")
    return 0


def _cmd_synthesize(args: argparse.Namespace) -> int:
    if args.text_file:
        text = Path(args.text_file).read_text(encoding="utf-8")
    elif args.text:
        text = args.text
    else:
        text = sys.stdin.read()
    if args.max_chars:
        text = text[: args.max_chars]
    output = Path(args.output) if args.output else None
    out = synthesize(args.provider, text, output)
    print(out)
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="云 TTS 配置与调用")
    sub = parser.add_subparsers(dest="command", required=True)

    p = sub.add_parser("list", help="列出配置与非敏感状态")
    p.set_defaults(func=_cmd_list)

    p = sub.add_parser("show", help="查看单个 provider 配置")
    p.add_argument("provider", choices=sorted(PROVIDER_PRESETS))
    p.set_defaults(func=_cmd_show)

    p = sub.add_parser("set-secret", help="把 Key 写入 Keychain")
    p.add_argument("provider", choices=sorted(PROVIDER_PRESETS))
    p.add_argument("secret")
    p.set_defaults(func=_cmd_set_secret)

    p = sub.add_parser("delete-secret", help="删除 Keychain 中的 Key")
    p.add_argument("provider", choices=sorted(PROVIDER_PRESETS))
    p.set_defaults(func=_cmd_delete_secret)

    p = sub.add_parser("synth", help="调用已配置的云 TTS")
    p.add_argument("provider", choices=sorted(PROVIDER_PRESETS))
    p.add_argument("--text")
    p.add_argument("--text-file")
    p.add_argument("--output")
    p.add_argument("--max-chars", type=int)
    p.set_defaults(func=_cmd_synthesize)
    return parser


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()
    try:
        return args.func(args)
    except CloudTTSError as exc:
        print(f"[x] {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
