export function installLocalStorageMock(): () => void {
  const original = window.localStorage;
  const store = new Map<string, string>();

  Object.defineProperty(window, "localStorage", {
    configurable: true,
    value: {
      get length() {
        return store.size;
      },
      clear: () => store.clear(),
      getItem: (key: string) => store.get(String(key)) ?? null,
      key: (index: number) => [...store.keys()][index] ?? null,
      removeItem: (key: string) => {
        store.delete(String(key));
      },
      setItem: (key: string, value: string) => {
        store.set(String(key), String(value));
      },
    },
  });

  return () => {
    Object.defineProperty(window, "localStorage", {
      configurable: true,
      value: original,
    });
  };
}
