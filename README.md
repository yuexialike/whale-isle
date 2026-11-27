# 鲸屿 Whale Isle

一个住在桌面上的小东西：站在屏幕底边，会走路、会冒气泡说话、能看见屏幕、能动手点鼠标。

## 这个项目没有模型

鲸屿**不做模型**：不训练、不发布权重、不打包任何模型文件。
脑子全靠调用现成的模型 API（默认 DeepSeek），换模型只改 `config.json`，不改代码。

## 它是什么

PySide6 写的桌面伴侣。外壳、人格、眼睛、手、嗓子、脑子、记忆各自一个文件，`main.py` 只负责把它们接起来。

  shell.py     壳      崩溃证据 / 送走旧的自己 / pid / 心跳
  persona.py   人格    读 CONSTITUTION / PARTNER / STATE，拼成脑子里的那段话
  gate.py      闸门    看屏幕 / 动手 / 终端，全从一个门
  ask.py       问句    「做吗」的小卡片
  body.py      身体    立绘、气泡、戳、走路
  hands.py     手      鼠标 / 键盘（ctypes SendInput，不经过输入法）
  screen.py    眼睛    抓屏 + 报坐标
  chat.py      耳朵    双击弹输入框
  page.py      对话页
  tts.py       嗓子
  llm.py       脑子
  memory.py    记忆    纯文本

## 怎么跑

    pip install PySide6 numpy
    python main.py

首次启动会在旁边生成 `data/` 和 `config.json`。要接大模型，在 config.json 里填 `api_key`，或者设环境变量 `DEEPSEEK_API_KEY`。

## 目录

- `figure/` 形象素材　`skin/` 皮肤　`plugins/` 插件
- `bridge/` 本地桥　`webui/` 网页界面
- `template/` 模板　`devkit/` 开发工具　`installer/` 打包

## 关于「门」

原版是闭的：一对 Ed25519 钥匙，私钥在作者手里，签出来的激活码只给某个人、某台机器，程序里还盖了封印防着改配置。
这份公开的版本把门拆了——`license.py` 和 `guard.py` 都是空实现，`check()` 永远放行，不用任何码。
想把门装回去，自己实现 `license.check()` 的返回就行，调用点没动过。

## 怎么更新

程序里「设置 → 关于」那一页有「检查更新」：

1. 点「检查更新」——它去读 `update.json`，有新版会把版号、日期和改了什么摆出来；
2. 点「下载」拿到 zip（会核对 sha256，对不上就不装）；
3. 点「试演」先看一遍会覆盖哪些文件、跳过哪些；
4. 点「安装」，然后重启程序。

清单地址（已经写进代码里，一般不用管）：
`https://raw.githubusercontent.com/yuexialike/whale-isle/main/update.json`

**从 v1.0.0 升上来的第一下要手动**：那一版的 `update_url` 是空的，点「检查更新」只会说
「还没配更新地址」。在同一个页面的地址框里粘一次上面那个地址、点「记住地址」，
之后就能一直自动走了。

装的时候这几个东西不会被覆盖：`config.json`、`data/`、`log/`、`people/`、`plugins/`、
`models/`、`skin/`、`updates/`。换坏了下不了台也没事：每次安装前旧文件都会存进
`updates/backup-<时间>/`，那一页的「回滚」把它铺回去。

## 许可

个人使用、学习、修改、再分发：免费。商业使用需事先书面授权。详见 [LICENSE](LICENSE)。

