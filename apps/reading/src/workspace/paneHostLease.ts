export type PaneHostLease<Record extends object> = {
  readonly record: Record;
  isCurrent: () => boolean;
  retire: () => boolean;
};

/** A cleanup owns the installed record, never the next occupant of its key. */
export function installPaneHostLease<Key, Record extends object>(
  registry: Pick<Map<Key, Record>, "get" | "delete"> & { set(key: Key, record: Record): void },
  key: Key,
  record: Record,
): PaneHostLease<Record> {
  let retired = false;
  registry.set(key, record);
  return {
    record,
    isCurrent: () => !retired && registry.get(key) === record,
    retire: () => {
      if (retired) return false;
      retired = true;
      return registry.get(key) === record && registry.delete(key);
    },
  };
}
