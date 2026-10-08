"""Run with browser-harness against guard:keymap:serve. Only HTTP is fixture data."""
import json
import os

from browser_harness.run import (
    cdp, click_at_xy, close_tab, goto_url, js, new_tab, press_key, wait_for_load,
)

BASE = os.environ.get("D2_ESCAPE_URL", "http://127.0.0.1:5196")


def emit(label, value):
    print(label, json.dumps(value), flush=True)


def wait(expression):
    return js(
        "new Promise((resolve,reject)=>{const start=performance.now();"
        "function check(){const value=(" + expression + ");if(value)return resolve(value);"
        "if(performance.now()-start>4000)return reject(Error('DOM condition timed out: '+"
        + json.dumps(expression) + "));setTimeout(check,25)}check()})"
    )


def state():
    return js("""({
      slash: !!document.querySelector('[data-notebook-editor] [role=listbox]'),
      palette: !!document.querySelector('[aria-label="Command palette"]'),
      focus: document.activeElement?.matches('[contenteditable=true]') ? 'editor'
        : document.activeElement?.closest('[aria-label="Command palette"]') ? 'palette'
        : document.activeElement?.tagName,
      viewport: [innerWidth,innerHeight]
    })""")


def trace():
    return js("escapeOwners.readKeyboardOwnership().traces.at(-1)")


def owners(trace, field):
    return [owner.split("#")[0] for owner in trace[field]]


target = new_tab("about:blank")
try:
    cdp("Emulation.setDeviceMetricsOverride", width=1440, height=900, deviceScaleFactor=1, mobile=False)
    # A visible macOS Chrome window can lack OS focus. CDP still sends trusted keys.
    cdp("Emulation.setFocusEmulationEnabled", enabled=True)
    init = cdp("Page.addScriptToEvaluateOnNewDocument", source="localStorage.clear();localStorage.setItem('antiek.motion','reduce');")
    goto_url(BASE + "/read/guard-a")
    wait_for_load()
    cdp("Page.removeScriptToEvaluateOnNewDocument", identifier=init["identifier"])
    wait("!!document.querySelector('[data-pane=left]')")
    js("import('/src/workspace/keyboardOwnership.ts').then(m=>{window.escapeOwners=m})")
    wait("escapeOwners.readKeyboardOwnership().registrations.some(r=>r.id==='workspace.direct')")
    mod = 4 if js("/Mac|iPhone|iPad/.test(navigator.platform)") else 2
    press_key("k", mod)
    wait("!!document.activeElement?.closest('[aria-label=\"Command palette\"]')")
    cdp("Input.insertText", text="Open new notebook (editor)")
    wait("document.querySelector('[aria-label=\"Command palette\"] input')?.value==='Open new notebook (editor)'")
    for _ in range(20):
        if js("document.querySelector('[aria-label=\"Command palette\"] li.bg-ice-3')?.textContent.includes('Open new notebook (editor)')"):
            break
        press_key("ArrowDown")
    else:
        raise AssertionError("The real palette did not offer the notebook command")
    press_key("Enter")
    wait("!!document.querySelector('[data-notebook-editor][data-hydrated=true] [contenteditable=true]')")
    editable = next(n for n in cdp("Accessibility.getFullAXTree")["nodes"]
                    if any(p.get("name") == "editable" and p.get("value", {}).get("value") == "richtext"
                           for p in n.get("properties", [])))
    box = cdp("DOM.getBoxModel", backendNodeId=editable["backendDOMNodeId"])["model"]["content"]
    click_at_xy(sum(box[0::2]) / 4, sum(box[1::2]) / 4)
    wait("document.activeElement?.matches('[contenteditable=true]')")
    press_key("/")
    wait("!!document.querySelector('[data-notebook-editor] [role=listbox]')")
    press_key("k", mod)
    wait("!!document.activeElement?.closest('[aria-label=\"Command palette\"]')")
    before = state()
    emit("BEFORE_ESCAPE", before)
    assert before["slash"] and before["palette"], before
    press_key("Escape")
    wait("!document.querySelector('[aria-label=\"Command palette\"]')")
    first, first_trace = state(), trace()
    emit("AFTER_FIRST_ESCAPE", first)
    emit("FIRST_ESCAPE_TRACE", first_trace)
    press_key("Escape")
    wait("!document.querySelector('[data-notebook-editor] [role=listbox]')")
    second, second_trace = state(), trace()
    emit("AFTER_SECOND_ESCAPE", second)
    emit("SECOND_ESCAPE_TRACE", second_trace)
    assert first_trace["trusted"] and second_trace["trusted"], "Trusted browser keys required"
    assert first == {"slash": True, "palette": False, "focus": "editor", "viewport": [1440, 900]}, "One Escape closed two overlays or lost editor focus"
    assert second == {"slash": False, "palette": False, "focus": "editor", "viewport": [1440, 900]}, second
    for entry, owner in [(first_trace, "palette.escape"), (second_trace, "notebook.slash-menu")]:
        assert owners(entry, "eligible") == [owner], entry
        assert owners(entry, "delivered") == [owner], entry
    emit("PASS", {"oneEscapeOneOverlay": True, "trusted": True, "productionObserved": False})
finally:
    close_tab(target)
