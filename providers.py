"""别家的脑子：一家一条，接口地址和常用模型名都替人填好。

月下 19:19：「这个连接模型的话，万一有人不用 deepseek 呢，我们是不是要把每一个
模型选项都加进去，然后把接口地址都能弄过来这种。」
19:23 又补：「你都写英文名吧，除了像千问这种没有英文名字——硅基流动，谁能想到他是。」

所以按钮上尽量写英文名（SiliconFlow、OpenRouter 这种本来就是英文的牌子），
中文名字挪到下面那行小字里认人。全是 **OpenAI 兼容** 的 `/chat/completions`——
鲸屿的 client 只认这一种，别家的私有协议（Anthropic 原生、Gemini 原生）不放进来。

模型名会变（各家改得比谁都快），这里只是「填好给你改」，填错了报 404，
在模型那一栏直接改就行。
"""
from __future__ import annotations

# id, 按钮上的名字, 接口地址, 常用模型（第一个当默认）, 下面那行小字
PROVIDERS: list[tuple[str, str, str, list[str], str]] = [
    ("deepseek", "DeepSeek", "https://api.deepseek.com/v1",
     ["deepseek-chat", "deepseek-reasoner"],
     "深度求索 · 便宜、中文顺，鲸屿默认这家。"),

    ("openai", "OpenAI", "https://api.openai.com/v1",
     ["gpt-4o-mini", "gpt-4o"],
     "要能连出去；国内不一定通。"),

    ("claude", "Claude", "https://api.anthropic.com/v1",
     ["claude-haiku-4-5", "claude-sonnet-4-5"],
     "Anthropic · 原生协议不一样，这里走它那个 OpenAI 兼容层，不稳就换 OpenRouter。"),

    ("gemini", "Gemini", "https://generativelanguage.googleapis.com/v1beta/openai",
     ["gemini-2.5-flash", "gemini-2.5-pro"],
     "Google · 地址后面带 /openai 的那条才是兼容口。"),

    ("qwen", "千问", "https://dashscope.aliyuncs.com/compatible-mode/v1",
     ["qwen-plus", "qwen-max", "qwen-turbo"],
     "通义千问 · 阿里云百炼控制台拿 key。"),

    ("kimi", "Kimi", "https://api.moonshot.cn/v1",
     ["moonshot-v1-8k", "moonshot-v1-32k"],
     "月之暗面 · 长文好使。"),

    ("zhipu", "GLM", "https://open.bigmodel.cn/api/paas/v4",
     ["glm-4-flash", "glm-4-plus"],
     "智谱 · 有免费额度的那档叫 flash。"),

    ("siliconflow", "SiliconFlow", "https://api.siliconflow.cn/v1",
     ["deepseek-ai/DeepSeek-V3", "Qwen/Qwen2.5-7B-Instruct"],
     "硅基流动 · 一家转卖很多开源模型，模型名带斜杠。"),

    ("openrouter", "OpenRouter", "https://openrouter.ai/api/v1",
     ["openai/gpt-4o-mini", "anthropic/claude-3.5-sonnet"],
     "一个 key 转着用各家，模型名带斜杠。"),

    ("ollama", "Ollama", "http://127.0.0.1:11434/v1",
     ["qwen2.5:7b", "llama3.1:8b"],
     "本地跑的 · 不花钱、不出网；key 随便填几个字。"),

    ("custom", "Custom", "", [],
     "自己填 · 接口只要兼容 OpenAI 的 /chat/completions 就能用。"),
]

BY_ID = {p[0]: p for p in PROVIDERS}


def guess_id(base: str, model: str) -> str:
    """从已经存着的地址和模型名认一下是哪家，认不出就 custom。"""
    b = (base or "").strip().lower()
    for pid, _name, url, _models, _note in PROVIDERS:
        if pid == "custom" or not url:
            continue
        if b and (b.startswith(url.lower()) or url.lower().split("//")[-1].split("/")[0] in b):
            return pid
    m = (model or "").strip().lower()
    if m.startswith("deepseek"):
        return "deepseek"
    if m.startswith("qwen"):
        return "qwen"
    if m.startswith("glm"):
        return "zhipu"
    if m.startswith("moonshot") or m.startswith("kimi"):
        return "kimi"
    if m.startswith("claude"):
        return "claude"
    if m.startswith("gemini"):
        return "gemini"
    return "custom"
