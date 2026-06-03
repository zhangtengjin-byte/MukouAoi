"""
Mukou Aoi — Mode Switch Plugin
================================
@work / @life mode switching for Hermes Agent.

- @work: No extra constraints. Full-length professional responses.
- @life: Word limit injected (user input × configured multiplier). Relaxed style.

@install
  Copy this directory to ~/.hermes/hermes-agent/plugins/mode-switch/
  and enable in config.yaml:
    plugins:
      mode-switch:
        enabled: true
"""

from pathlib import Path

PLUGIN_DIR = Path(__file__).parent
MODE_FILE = PLUGIN_DIR / "mode.txt"


def get_mode():
    if MODE_FILE.exists():
        return MODE_FILE.read_text().strip()
    return "work"


def set_mode(mode: str):
    MODE_FILE.write_text(mode)


def register(ctx):
    def pre_gateway_dispatch(event=None, gateway=None, session_store=None, **kwargs):
        if not event:
            return
        text = (getattr(event, "text", "") or "").strip()
        if text in ("@work", "/work"):
            set_mode("work")
            return {"action": "skip", "reason": "mode switched to work"}
        if text in ("@life", "/life"):
            set_mode("life")
            return {"action": "skip", "reason": "mode switched to life"}
        return

    ctx.register_hook("pre_gateway_dispatch", pre_gateway_dispatch)

    def pre_llm_call(user_message="", **kwargs):
        if not user_message:
            return
        mode = get_mode()
        if mode == "life":
            user_len = len(user_message.strip())
            # Multiplier: user input length × 2 (default). Configurable via mode.life_multiplier
            word_limit = user_len * 2
            return {"context": f"务必遵守字数限制。本次回复少于{word_limit}字。"}
        # work mode: no injection
        return

    ctx.register_hook("pre_llm_call", pre_llm_call)

    def mode_switch(args, **kwargs):
        mode = args.get("mode")
        if mode not in ["work", "life"]:
            return {"error": "无效模式，可选: work, life"}
        set_mode(mode)
        return {"ok": True, "mode": mode}

    ctx.register_tool(
        name="mode_switch",
        toolset="mode",
        schema={
            "type": "object",
            "properties": {
                "mode": {"type": "string", "description": "work 或 life"}
            },
            "required": ["mode"],
        },
        handler=mode_switch,
    )

    def mode_status(args=None, **kwargs):
        return {"mode": get_mode()}

    ctx.register_tool(
        name="mode_status",
        toolset="mode",
        schema={"type": "object", "properties": {}},
        handler=mode_status,
    )
