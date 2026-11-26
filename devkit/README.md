# 鲸屿 · 插件开发包（devkit）

一个插件 = **一个 `.py` 文件**。放进 `plugins/`，在 `config.json` 的 `plugins` 里点上名，重启就生效。
不用编译、不用打包、不用注册表。这一页就是全部规范。

---

## 一、最小可用的插件

```python
NAME  = "现在几点"
ABOUT = "让它知道今天几号、现在几点。一个工具：now。"

def _now(_args):
    import datetime as dt
    return f"现在 {dt.datetime.now():%Y-%m-%d %H:%M}"

TOOLS = [(
    {"type": "function",
     "function": {"name": "now",
                  "description": "现在几点、今天几号星期几（本机时间）。",
                  "parameters": {"type": "object", "properties": {}}}},
    _now,
)]
```

存成 `plugins/time_now.py`，`config.json` 里写 `"plugins": ["time_now"]`，重启。完事。
`devkit/template.py` 是带设置项和状态的完整版，照它改最快。

## 二、能写的东西

| 名字 | 必需 | 是什么 |
|---|---|---|
| `NAME` | 建议 | 给人看的名字 |
| `ABOUT` | 建议 | 一句话说明，设置页和市场列表都显示它 |
| `ICON` | 可选 | 两个字的图标字，比如 `"时"` |
| `TOOLS` | 必需* | `[(schema, 函数), …]`，形状跟 OpenAI function schema 一致；函数收一个 `args` 字典，返回字符串 |
| `setup(ctx)` | 可选 | 装的时候跑一次；拿 `ctx` 里的东西（见下） |
| `status()` | 可选 | 返回 `(亮不亮: bool, 一句话)`，设置页那盏状态灯用它 |
| `SETTINGS` | 可选 | `[{key,label,kind,hint}]`，`kind` 只能是 `text` / `int` / `bool` / `lines`；设置页照着它自己长界面 |
| `SETTINGS_SECTION` | 可选 | 设置存到 `config.json` 的哪一格，默认跟插件名同名 |

\* 只想「自己冒头」、不提供工具的插件可以不写 `TOOLS`，但得在 `setup(ctx)` 里用 `ctx["hooks"]` 挂上来源。

## 三、`ctx` 里有什么

```python
def setup(ctx):
    say   = ctx["say"]        # 直接冒个泡（不过脑子）：say("连不上了")
    tools = ctx["tools"]      # 核心工具模块：tools.register / tools.call ...
    cfg   = ctx["config"]     # 整个 config.json 的字典（只读）
    data  = ctx["data_dir"]   # 你的私有数据目录，自己的东西只往这儿写
    ws    = ctx["workspace"]  # 工作区（记忆文件那一堆）
    body  = ctx["body"]       # 能指挥身体做动作
    hooks = ctx["hooks"]      # 见下一节
```

## 四、想主动说话：hooks

插件默认只能被叫。要「自己冒头」，只有这三条路：

```python
ctx["hooks"].push("QQ 来消息了：……")   # 塞进下一轮上下文，取一次就清空
ctx["hooks"].wake("QQ 来消息了")        # 立刻起一轮，不等心跳
ctx["hooks"].say("连不上 QQ 了")        # 不过脑子，直接冒泡
```

**`wake` 起的那一轮不许动电脑**——这是规矩，不是建议。要动电脑，得是人在桌宠那边说了话。

## 五、硬规矩（校验器会拦）

1. **只能用标准库。** 要第三方包先在文档里写清楚，别偷偷 `import requests`。
2. **不许 `eval` / `exec` / `os.system` / `subprocess` / `__import__` 动态导入。**
   要起外部程序，走核心的 `run_command` 工具，让人点头。
3. **只往 `data_dir` 写。** 别碰人家的桌面、文档、别的地方。
4. **联网要先说。** 请求一律带 20 秒超时，失败了返回一句人话，别抛栈。
5. **不写死路径、不写死别人家的 key。** 配置从 `SETTINGS` 来。
6. **一个文件一个插件。** 超过 500 行就该拆思路，不是拆文件。

## 六、自测

```bat
py -3 devkit\check.py plugins\你的插件.py
```

它会：查语法 → 查必需字段 → 查危险调用 → 查工具名重复 → 数行数。
全绿之后再 `import` 跑一遍，把 `TOOLS` 里每个函数都拿空字典 `{}` 调一次，
**每个都要能返回一句人话，不许抛异常**。工具是最容易被模型乱调的入口。

## 七、装给别人

开发机上直接放 `plugins/` 就行。发给别人只有一条：
把那个 `.py` 的直链给他，他在设置页「装插件」里填链接——核心会先下回来、
先 `ast` 解析一遍，语法不对的不进家门，再问他要不要覆盖同名的。

所以分发要准备的就一样：**一个能直链的地址**（GitHub raw、gitee raw、自己的静态空间都行）。
