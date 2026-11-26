"""3-2 真机夹具：只为验「装上一个、卸干净」。不属于产品，验完删。"""
import os
import threading

MANIFEST = {"id": "fixtureprobe", "name": "Fixture", "version": "0.1", "api": 1}
NAME = "Fixture"
_state = {"ev": None, "mark": ""}


def _tool(args):
    return "fixture-ok:" + str((args or {}).get("x", ""))


TOOLS = [({"type": "function", "function": {"name": "fixture_echo", "description": "d",
          "parameters": {"type": "object", "properties": {}}}}, _tool)]


def _loop():
    ev = _state["ev"]
    while not ev.wait(0.05):
        pass


def start(ctx):
    _state["mark"] = os.path.join(str(ctx.get("data_dir") or "."), "fixture-start.txt")
    open(_state["mark"], "w").write("1")
    _state["ev"] = threading.Event()
    threading.Thread(target=_loop, daemon=True, name="fixture-worker").start()


def stop():
    ev = _state.get("ev")
    if ev:
        ev.set()
    open(os.path.join(os.path.dirname(_state["mark"]), "fixture-stop.txt"), "w").write("1")