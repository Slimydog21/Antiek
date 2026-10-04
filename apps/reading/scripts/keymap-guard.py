# Run with browser-harness < scripts/keymap-guard.py. Chrome keys come from CDP,
# never dispatchEvent(new KeyboardEvent(...)). Use a disposable browser/profile.
import json
import os
import sys
import time

BASE = os.environ.get("D2_GUARD_URL", "http://127.0.0.1:5196")
ONLY = os.environ.get("D2_GUARD_ONLY", "")
PLATFORMS = os.environ.get("D2_GUARD_PLATFORMS", "mac,other").split(",")
failures = []
results = []

def call(expression):
    js("window.__guardJob={done:false};Promise.resolve().then(()=>eval(%s)).then(value=>window.__guardJob={done:true,value},error=>window.__guardJob={done:true,error:String(error)});undefined" % json.dumps(expression))
    deadline = time.monotonic() + 30
    while time.monotonic() < deadline:
        result = js("new Promise(resolve=>setTimeout(()=>resolve(window.__guardJob),40))")
        if result and result.get("done"):
            if result.get("error"): raise RuntimeError(result["error"])
            return result.get("value")
    raise RuntimeError("browser operation exceeded 30 seconds: " + expression)


def press(spec, platform):
    parts = spec.lower().split("+")
    key = parts[-1]
    mods = set(parts[:-1])
    if "mod" in mods:
        mods.remove("mod")
        mods.add("meta" if platform == "mac" else "ctrl")
    code = {"[":"BracketLeft", "]":"BracketRight", "/":"Slash", "?":"Slash", ";":"Semicolon", "escape":"Escape"}.get(key, "Key" + key.upper())
    if key == "?": mods.add("shift")
    mask = sum({"alt":1,"ctrl":2,"meta":4,"shift":8}[m] for m in mods)
    actual = "Escape" if key == "escape" else key.upper() if "shift" in mods and key.isalpha() else key
    # Chromium's US Mac ctrl+option printable character in text, not synthetic DOM.
    in_text = call("!!document.activeElement?.matches('input,textarea,[contenteditable=true]')")
    if platform == "mac" and "alt" in mods and in_text:
        actual = {"b":"∫","h":"˙","l":"¬","f":"ƒ", "c":"ç","u":"¨","o":"ø","y":"¥","i":"ˆ","p":"π","[":"“","]":"‘"}.get(key, key)
    cdp("Input.dispatchKeyEvent", type="keyDown", key=actual, code=code, modifiers=mask)
    cdp("Input.dispatchKeyEvent", type="keyUp", key=actual, code=code, modifiers=mask)

def dismiss():
    for _ in range(3):
        cdp("Input.dispatchKeyEvent", type="keyDown", key="Escape", code="Escape")
        cdp("Input.dispatchKeyEvent", type="keyUp", key="Escape", code="Escape")

def alias(row, platform, prefix="ctrl+b"):
    if row.get("prefixKey"):
        press(prefix, platform)
        press(row["prefixKey"], platform)
    else:
        press(row["chord"], platform)

for platform in PLATFORMS:
    target = new_tab("about:blank")
    activate_tab(target)  # Disposable headless tab: background timers otherwise throttle fixture waits.
    cdp("Emulation.setDeviceMetricsOverride", width=1440, height=1000, deviceScaleFactor=1, mobile=False)
    cdp("Page.addScriptToEvaluateOnNewDocument", source="Object.defineProperty(navigator, 'platform', {get: () => %s});localStorage.clear();localStorage.setItem('antiek.motion','reduce');" % json.dumps("MacIntel" if platform == "mac" else "Linux x86_64"))
    try:
        goto_url(BASE + "/read/guard-a")
        wait_for_load()
        call("(async()=>{window.d2Guard=await import('/scripts/keymap-guard.scenarios.ts');await d2Guard.until(()=>!!document.querySelector('[data-pane=left], [data-cockpit-content]'),'real AppShell did not mount',12000);})()")
        rows = call("d2Guard.manifest()")
        exercised = []
        sheet_rows = []
        for row in rows:
            if ONLY and ONLY not in (row["id"], row["action"]): continue
            try:
                dismiss()
                prepared = call("d2Guard.prepare(%s)" % json.dumps(row["id"]))
                alias(row, platform, prepared["prefix"])
                exercised.append(row["id"])
                result = call("d2Guard.verify(%s)" % json.dumps(row["id"]))
                results.append({"platform":platform, "context":"default", **result})
                print("PASS", platform, row["id"], row["action"], flush=True)
                if row["action"] == "keysheet.toggle":
                    sheet_rows = call("[...document.querySelectorAll('[data-keymap-row]')].map(e=>e.dataset.keymapRow)")
                # Every alias is also pressed from text. Any advertised anywhere
                # chord that does not type is required to produce the same effect.
                if os.environ.get("D2_GUARD_SCOPES", "1") == "1":
                    dismiss()
                    prepared = call("d2Guard.prepare(%s,'text')" % json.dumps(row["id"]))
                    alias(row, platform, prepared["prefix"])
                    effect = row["scope"] == "anywhere" and not (platform == "mac" and "alt+" in row.get("chord", ""))
                    scoped = call("d2Guard.verify(%s,%s)" % (json.dumps(row["id"]),str(effect).lower()))
                    results.append({"platform":platform, "context":"text", **scoped})
                    print("PASS", platform, "text", row["id"], row["action"], flush=True)
                    dismiss()
                    prepared = call("d2Guard.prepare(%s,'modal')" % json.dumps(row["id"]))
                    alias(row, platform, prepared["prefix"])
                    scoped = call("d2Guard.verify(%s,false)" % json.dumps(row["id"]))
                    results.append({"platform":platform, "context":"modal", **scoped})
                    print("PASS", platform, "modal", row["id"], row["action"], flush=True)
            except Exception as error:
                failure = f"{platform} {row['id']}/{row['action']}: {error}"
                failures.append(failure)
                print("FAIL", failure, flush=True)
                print("OWNER TRACE", json.dumps(call("d2Guard.readKeyboardOwnership().traces.slice(-4)")), flush=True)
        if not ONLY:
            try:
                dismiss()
                call("d2Guard.setupDialogs()")
                press("escape", platform)
                results.append({"platform":platform,"context":"stacked-modal-upper","traces":call("d2Guard.verifyDialogs(1)")})
                press("escape", platform)
                results.append({"platform":platform,"context":"stacked-modal-lower","traces":call("d2Guard.verifyDialogs(0)")})
                call("d2Guard.prepare('projecttree','editor')")
                press("mod+z", platform)
                results.append({"platform":platform,"context":"editor-observer","traces":call("d2Guard.verifyObserver()")})
                press("mod+b", platform)
                call("d2Guard.verify('projecttree',false)")
                call("d2Guard.setupFrame()")
                press("mod+e", platform)
                results.append({"platform":platform,"context":"iframe","outcome":call("d2Guard.verifyFrame()")})
                call("d2Guard.setPrefix('ctrl+a')")
                prepared = call("d2Guard.prepare('prefix-sidebar')")
                alias(next(r for r in rows if r["id"] == "prefix-sidebar"), platform, prepared["prefix"])
                results.append({"platform":platform,"context":"custom-prefix",**call("d2Guard.verify('prefix-sidebar')")})
                call("d2Guard.setPrefix(null)")
                print("PASS FINITE CONTEXTS",platform,"stacked dialogs/editor observer/iframe/custom prefix",flush=True)
            except Exception as error:
                failures.append(f"FINITE CONTEXTS {platform}: {error}")
                print("FAIL FINITE CONTEXTS",platform,error,flush=True)
            try:
                population = call("d2Guard.population(%s,%s)" % (json.dumps(exercised),json.dumps(sheet_rows)))
                print("PASS POPULATION", platform, json.dumps(population), flush=True)
            except Exception as error:
                failures.append(f"POPULATION {platform}: {error}")
                print("FAIL POPULATION", platform, error, flush=True)
    except Exception as error:
        failures.append(f"FIXTURE {platform}: {error}")
        print("FAIL FIXTURE", platform, error, flush=True)
        print("DOM", js("document.body.innerText.slice(0,2500)"), flush=True)
        print("EXCEPTIONS", [x.get("params",{}).get("exceptionDetails",{}).get("exception",{}).get("description") for x in drain_events() if x.get("method") == "Runtime.exceptionThrown"][-5:], flush=True)
    finally:
        close_tab(target)

out = os.environ.get("D2_GUARD_RESULT", "keymap-guard-result.json")
with open(out, "w") as stream: json.dump({"results":results,"failures":failures},stream,indent=2)
print(f"SUMMARY {len(results)} exercised contexts; {len(failures)} failures; {out}")
if failures: sys.exit(1)
