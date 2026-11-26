"""耳朵：录音 + 听写。

听写用的是 **SenseVoiceSmall**（FunASR 那个，Coop 也用它），
模型文件直接复用硬盘上已有的那份，不重新下载：
    C:\\Users\\user\\Coopanion\\data\\home\\models\\desktop-pet\\sensevoice-small-int8-2024-07-17\\
引擎是 sherpa-onnx（pip 装的 Python 版，自带 onnxruntime，不碰 torch）。

为什么用这个而不是别的：
  - 228MB，int8，中文强（中英日韩粤），5060 上跑得很快；
  - Coop 用的就是同一份 —— 如果接过来还是听不准，那就不是模型的问题，
    是麦克风、断句（VAD）或者离太远，换模型也救不了。

断句很简单：听到声音开始记，连续静音 quiet_sec 秒就收句；最长 max_sec 兜底。
"""
from __future__ import annotations

import os
import sys
import wave
from array import array
from pathlib import Path

SAMPLE_RATE = 16000
# 设置页里挑的那个麦克风（设备号、或者名字里的一段字）。空 = 用系统默认。
DEFAULT_DEVICE = ""
MODEL_ID = "sensevoice-small-int8-2024-07-17"


def _home() -> Path:
    """程序和它的东西在哪：打包后是 exe 所在目录。"""
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parent


def models_dir() -> Path:
    """模型根目录：WHALE_MODELS → config.models_dir → 程序旁边的 models/。"""
    env = os.environ.get("WHALE_MODELS", "").strip()
    if env:
        return Path(env)
    try:
        import memory
        cfg_dir = str((memory.load_config() or {}).get("models_dir") or "").strip()
        if cfg_dir:
            return Path(cfg_dir)
    except Exception:                       # noqa: BLE001
        pass
    return _home() / "models"


def model_dir() -> Path:
    return models_dir() / "desktop-pet" / MODEL_ID


MODEL_DIR = model_dir()

_recognizer = None


def available() -> bool:
    return (MODEL_DIR / "model.int8.onnx").is_file() and (MODEL_DIR / "tokens.txt").is_file()


def recognizer():
    """开一次就留着，重建一次要好几秒。"""
    global _recognizer
    if _recognizer is not None:
        return _recognizer
    import sherpa_onnx

    _recognizer = sherpa_onnx.OfflineRecognizer.from_sense_voice(
        model=str(MODEL_DIR / "model.int8.onnx"),
        tokens=str(MODEL_DIR / "tokens.txt"),
        num_threads=2,
        use_itn=True,          # 数字、标点让它自己整理
        language="auto",
        debug=False,
    )
    return _recognizer


# ---------------------------------------------------------------- 听写

def _resample(pcm, rate: int, target: int):
    """线性重采样。听写够用，不引 torch（起一次要好几秒）。"""
    import numpy as np

    if rate == target:
        return pcm
    n = int(round(len(pcm) * target / rate))
    if n <= 1:
        return pcm
    x_old = np.linspace(0.0, 1.0, len(pcm), endpoint=False)
    x_new = np.linspace(0.0, 1.0, n, endpoint=False)
    return np.interp(x_new, x_old, pcm).astype("float32")


def transcribe_file(path: str | Path, sample_rate: int = SAMPLE_RATE) -> str:
    """听一个 wav。回来是文字，没听清就是空串。不是 16k 的会先重采样。"""
    import numpy as np

    with wave.open(str(path), "rb") as w:
        rate = w.getframerate()
        channels = w.getnchannels()
        width = w.getsampwidth()
        raw = w.readframes(w.getnframes())

    if width != 2:
        raise ValueError(f"只认 16bit 的 wav，这个是 {width * 8}bit")
    pcm = np.frombuffer(raw, dtype="<i2").astype("float32") / 32768.0
    if channels > 1:
        pcm = pcm.reshape(-1, channels).mean(axis=1)
    pcm = _resample(pcm, rate, sample_rate)

    return transcribe_samples(pcm, sample_rate)


def transcribe_samples(samples, sample_rate: int = SAMPLE_RATE) -> str:
    rec = recognizer()
    stream = rec.create_stream()
    stream.accept_waveform(sample_rate, samples)
    rec.decode_stream(stream)
    return (stream.result.text or "").strip()


def looks_like_speech(text: str) -> bool:
    """SenseVoice 对无声/噪声会吐标签（[Music]、[Noise]…）或空。"""
    t = text.strip()
    if not t:
        return False
    low = t.lower()
    for tag in ("[music]", "[noise]", "[applause]", "[laughter]", "[silence]", "<|nospeech|>"):
        if low.replace(" ", "") == tag:
            return False
    return True


# ---------------------------------------------------------------- 录音

def listen_once(quiet_sec: float = 0.9, max_sec: float = 20.0,
                start_timeout: float = 0.0, sample_rate: int = SAMPLE_RATE) -> tuple[str, float]:
    """录一句，听完写字。回来 (文字, 用了多少秒)。

    start_timeout > 0 时：这么久还没听到有人说话就不录了，回 ("", 秒)。
    """
    import numpy as np
    import sounddevice as sd

    block = 0.1                                   # 每次读 100ms
    frame = int(sample_rate * block)
    quiet_blocks = max(1, int(quiet_sec / block))
    max_blocks = int(max_sec / block)
    start_blocks = int(start_timeout / block) if start_timeout > 0 else 0

    buf: list = []
    spoken = False
    silent_run = 0
    waited = 0
    threshold = 0.012                             # 简单门限，够用；小声就调低

    with open_mic(sample_rate) as mic:
        for i in range(max_blocks + start_blocks):
            data, _ = mic.read(frame)
            mono = data[:, 0].copy()
            loud = float(np.abs(mono).max())
            if not spoken:
                if loud >= threshold:
                    spoken = True
                    buf.append(mono)
                elif start_blocks and i >= start_blocks:
                    return "", i * block
                continue
            buf.append(mono)
            if loud < threshold:
                silent_run += 1
                if silent_run >= quiet_blocks:
                    break
            else:
                silent_run = 0

    if not buf:
        return "", 0.0
    samples = np.concatenate(buf)
    text = transcribe_samples(samples, sample_rate)
    return text, len(samples) / sample_rate


def save_wav(samples, path: str | Path, sample_rate: int = SAMPLE_RATE) -> None:
    """留个底（调试用）。samples 是 -1~1 的 float。"""
    pcm = array("h", [int(max(-1.0, min(1.0, s)) * 32767) for s in samples])
    with wave.open(str(path), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(sample_rate)
        w.writeframes(pcm.tobytes())


# ---------------------------------------------------------------- 按键说话

# 名字 → 虚拟键码（GetAsyncKeyState 用的）
VK_NAMES = {
    "f7": 0x76, "f8": 0x77, "f9": 0x78, "f10": 0x79, "f11": 0x7A, "f12": 0x7B,
    "rightctrl": 0xA3, "rctrl": 0xA3, "rightalt": 0xA5,
    "capslock": 0x14, "scrolllock": 0x91, "pause": 0x13,
    "insert": 0x2D, "home": 0x24, "end": 0x23,
}


def resolve_vk(name) -> int:
    """'f9' / 'rightctrl' / 0x78 / '120' 都能认，认不出就回 F9。"""
    if isinstance(name, int):
        return name
    s = str(name or "").strip().lower()
    if not s:
        return VK_NAMES["f9"]
    if s in VK_NAMES:
        return VK_NAMES[s]
    try:
        return int(s, 0)
    except ValueError:
        return VK_NAMES["f9"]


def key_down(vk: int) -> bool:
    """这个键现在按着没有。不用装钩子，问一下系统的键状态就够。"""
    import ctypes
    return bool(ctypes.windll.user32.GetAsyncKeyState(vk) & 0x8000)


BLOCK = 0.05


def list_input_devices() -> list[dict]:
    """列出能录音的设备。返回 [{index, name, channels, rate, default}]。

    11-06 15:55 照 Coop 0.2.18 的「选择具体的麦克风」：以前只能让系统挑默认，
    他一插耳机、一开会，声音就不知道跑哪去了。
    """
    try:
        import sounddevice as sd
        devs = sd.query_devices()
        try:
            default_in = sd.default.device[0]
        except Exception:
            default_in = -1
    except Exception:
        return []
    out = []
    seen = set()
    for i, d in enumerate(devs):
        try:
            if int(d.get("max_input_channels", 0)) <= 0:
                continue
        except Exception:
            continue
        name = str(d.get("name", ""))
        low = name.lower()
        # 一堆声卡驱动把「扬声器/回放」也报成能录音（回环），挑麦克风时只会看花眼
        if "扬声器" in name or "output" in low or "loopback" in low:
            continue
        # 微软的老映射器，真选它反而绕一圈，列出来只添乱
        if "映射器" in name or "mapper" in low or "主声音" in name:
            continue
        key = low.split("(")[0].strip()        # 同一个设备按采样率/主机接口重复报几条，只留第一条
        if key in seen:
            continue
        seen.add(key)
        out.append({
            "index": i,
            "name": name,
            "channels": int(d.get("max_input_channels", 1)),
            "rate": int(d.get("default_samplerate", SAMPLE_RATE)),
            "default": i == default_in,
        })
    out.sort(key=lambda x: (not x["default"], x["index"]))   # 系统默认那个排最前
    return out


def find_device(want) -> int | None:
    """把设置里存的东西认成一个设备号。

    存的东西可能是：空（用默认）、设备号、"名字里的一段字"。
    找不到就返回 None —— 由调用方退回系统默认，绝不硬顶着报错。
    """
    if want is None or want == "":
        return None
    try:
        idx = int(want)
    except (TypeError, ValueError):
        idx = None
    devs = list_input_devices()
    if idx is not None:
        for d in devs:
            if d["index"] == idx:
                return idx
        return None
    key = str(want).strip().lower()
    for d in devs:                       # 先找一模一样的名字，再找包含
        if d["name"].strip().lower() == key:
            return d["index"]
    for d in devs:
        if key in d["name"].strip().lower():
            return d["index"]
    return None


def open_mic(sample_rate: int = SAMPLE_RATE, device=None):
    """开一次麦克风，长期用着。

    11-04 19:05：以前是每按一次 F9 就 `with sd.InputStream(...)` 开一次、关一次。
    关流那一下（PortAudio 的 close）在 Windows 上偶尔把堆搞坏——
    crash.log 里那条 `0xc0000374` 就是它，硬崩，连日志都来不及写。
    所以改成整条命只开一次、不关；进程没了流自然跟着没。

    11-06：device 可以是设备号、设备名的一段字，或者 None（用系统默认）。
    认不出来就当没填——拔了麦克风也不会连累整条耳朵。
    """
    import sounddevice as sd

    idx = find_device(device if device not in (None, "") else DEFAULT_DEVICE)
    kwargs = {"samplerate": sample_rate, "channels": 1, "dtype": "float32",
              "blocksize": int(sample_rate * BLOCK)}
    if idx is not None:
        kwargs["device"] = idx
    try:
        mic = sd.InputStream(**kwargs)
        mic.start()
        return mic
    except Exception:
        if idx is None:
            raise
        kwargs.pop("device", None)          # 选中的那个不在（拔了 / 被占），退回系统默认
        mic = sd.InputStream(**kwargs)
        mic.start()
        return mic


def listen_hold(vk: int = 0x78, max_sec: float = 30.0, tail_sec: float = 0.25,
                sample_rate: int = SAMPLE_RATE, mic=None,
                on_press=None) -> tuple[str, float]:
    """按住说话：按住 vk 才录，松开就收句。回来 (文字, 用的秒数)。

    麦克风一直开着（开一次要百来毫秒，按下去再开就丢前一个字），
    只在按住的时候把数据留下来。松开后再留一点点尾巴，别把最后一个字切掉。
    `mic` 传进来就用它（见 open_mic），不传就自己开一次、用完关掉。
    """
    import numpy as np
    import sounddevice as sd

    block = BLOCK
    frame = int(sample_rate * block)
    max_blocks = int(max_sec / block)
    tail_blocks = max(1, int(tail_sec / block))

    def _hold(mic) -> list:
        buf: list = []
        held = False
        idle = 0
        while True:
            data, _ = mic.read(frame)
            down = key_down(vk)
            if down:
                if not held and on_press is not None:
                    try:
                        on_press(True)          # 按下了：界面上亮「在听……」
                    except Exception:           # noqa: BLE001
                        pass
                held = True
                idle = 0
                buf.append(data[:, 0].copy())
                if len(buf) >= max_blocks:
                    break
                continue
            if held:
                buf.append(data[:, 0].copy())
                idle += 1
                if idle >= tail_blocks:
                    break
            # 还没按下：这一块直接扔了
        return buf

    if mic is not None:
        buf = _hold(mic)
    else:
        with open_mic(sample_rate) as own:
            buf = _hold(own)

    if not buf:
        return "", 0.0
    samples = np.concatenate(buf)
    if float(np.abs(samples).max()) < 0.012:      # 按了但没说话
        return "", len(samples) / sample_rate
    return transcribe_samples(samples, sample_rate), len(samples) / sample_rate
