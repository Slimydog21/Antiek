function makeMemoryStorage(): Storage {
  const values = new Map<string, string>();

  return {
    get length() {
      return values.size;
    },
    clear() {
      values.clear();
    },
    getItem(key: string) {
      return values.has(key) ? values.get(key)! : null;
    },
    key(index: number) {
      return Array.from(values.keys())[index] ?? null;
    },
    removeItem(key: string) {
      values.delete(key);
    },
    setItem(key: string, value: string) {
      values.set(key, String(value));
    },
  };
}

function hasUsableStorage(storage: Storage | undefined): storage is Storage {
  return (
    typeof storage?.clear === "function" &&
    typeof storage.getItem === "function" &&
    typeof storage.setItem === "function" &&
    typeof storage.removeItem === "function" &&
    typeof storage.key === "function"
  );
}

function installStorage(name: "localStorage" | "sessionStorage") {
  const scope = globalThis as typeof globalThis & {
    window?: Window;
    localStorage?: Storage;
    sessionStorage?: Storage;
  };
  const current = scope.window?.[name] ?? scope[name];
  if (hasUsableStorage(current)) {
    return;
  }

  const storage = makeMemoryStorage();
  Object.defineProperty(scope, name, {
    configurable: true,
    value: storage,
  });
  if (scope.window) {
    Object.defineProperty(scope.window, name, {
      configurable: true,
      value: storage,
    });
  }
}

installStorage("localStorage");
installStorage("sessionStorage");
