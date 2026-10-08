import { useEffect, useLayoutEffect, useRef, useState } from "react";

import { LemonModal } from "../components/lemon/LemonModal";
import { ErrorState, LoadingState } from "../components/states";
import { listProjects, type Project } from "../lib/api/projects";
import { useSelection } from "./contracts/selection";
import { TAB_PROJECT_ID, useTabTrees } from "./tabTreeStore";

/**
 * ProjectPickerContent — the account-project picker (lazy-loaded by
 * ProjectPicker): the registry's projects (lib/api/projects.ts,
 * THREAD-CONTRACT §1.5), one pick filing the tab trees under it
 * (contracts/selection.selectProject, the one writer, which calls
 * tabTreeStore.selectProject).
 *
 * The default project is always a row: it is where the trees file before
 * any choice, and picking it back clears the stored selection. Picking the
 * project already selected just closes. An archived project stays listed
 * only when it IS the selection (its tabs are still yours); the registry's
 * default list already excludes the rest.
 */

interface LoadState {
  status: "loading" | "ready" | "error";
  projects: Project[];
  /** The raw message, for "Copy error details" — never on screen. */
  detail: string | null;
}

/** One row: the default project, or a registry project. */
interface ProjectRow {
  id: string;
  title: string;
  subtitle: string;
}

function registryRow(p: Project): ProjectRow {
  const bits = [
    p.kind === "reading" ? "Reading" : "Project",
    `${p.member_count} member${p.member_count === 1 ? "" : "s"}`,
  ];
  if (p.pinned) bits.push("pinned");
  return { id: p.project_id, title: p.title, subtitle: bits.join(" · ") };
}

const DEFAULT_ROW: ProjectRow = {
  id: TAB_PROJECT_ID,
  title: "Default project",
  subtitle: "Where your tabs file before you choose a project",
};

export default function ProjectPickerContent({ onClose, initialFocusId }: { onClose: () => void; initialFocusId?: string }) {
  const projectId = useTabTrees((s) => s.projectId);
  const [load, setLoad] = useState<LoadState>({ status: "loading", projects: [], detail: null });
  const listRef = useRef<HTMLUListElement>(null);

  // SPR-04 gear 1: once the list is up, focus the row the switch asked for
  // (the modal's own trap put focus on the first focusable at mount, while
  // the list was still loading). An unknown id leaves the trap's choice.
  useEffect(() => {
    if (load.status !== "ready" || !initialFocusId) return;
    const row = [...(listRef.current?.querySelectorAll<HTMLButtonElement>("button[data-project-row]") ?? [])]
      .find((b) => b.dataset.projectRow === initialFocusId);
    row?.focus();
  }, [load.status, initialFocusId]);

  const reload = () => {
    setLoad((s) => ({ ...s, status: "loading", detail: null }));
    void listProjects()
      .then((projects) => setLoad({ status: "ready", projects, detail: null }))
      .catch((e: unknown) =>
        setLoad({
          status: "error",
          projects: [],
          detail: e instanceof Error ? e.message : String(e),
        }),
      );
  };

  useEffect(reload, []);

  // Give focus back, on close, to whatever had it when the picker opened
  // (KeySheet's pattern).
  useLayoutEffect(() => {
    const opener = document.activeElement;
    return () => {
      if (opener instanceof HTMLElement && opener.isConnected) opener.focus();
    };
  }, []);

  const choose = (id: string) => {
    onClose();
    useSelection.getState().selectProject(id);
  };

  const rows: ProjectRow[] = [DEFAULT_ROW, ...load.projects.map(registryRow)];

  return (
    <LemonModal open onClose={onClose} title="Account project" size="sm">
      <div data-keymap-owner="project.select">
        <p className="mb-3 text-xs text-shadow-1 dark:text-moonlight">
          Your tabs file under the project you pick; each project&rsquo;s tabs are its own.
        </p>

        {load.status === "loading" ? (
          <LoadingState variant="inline" label="Opening your projects" />
        ) : load.status === "error" ? (
          <ErrorState
            variant="inline"
            title="Couldn't open your projects"
            body="Your tabs are untouched; only the registry didn't answer."
            detail={load.detail}
            onRetry={reload}
          />
        ) : (
          <ul ref={listRef} className="max-h-[60vh] overflow-auto" aria-label="Projects">
            {rows.map((row) => {
              const current = row.id === projectId;
              return (
                <li key={row.id}>
                  <button
                    type="button"
                    data-project-row={row.id}
                    onClick={() => choose(row.id)}
                    aria-current={current ? "true" : undefined}
                    className="flex w-full items-center justify-between gap-3 rounded px-2 py-1.5 text-left hover:bg-ice-2 dark:hover:bg-charcoal-1 focus-visible:outline focus-visible:outline-2 focus-visible:outline-sun"
                  >
                    <span className="flex min-w-0 flex-col">
                      <span className="truncate text-sm text-ink dark:text-bright">{row.title}</span>
                      <span className="truncate text-xs text-shadow-1 dark:text-moonlight">
                        {row.subtitle}
                      </span>
                    </span>
                    {current ? (
                      <span className="shrink-0 font-mono text-xxs uppercase tracking-wider text-sun-ink">
                        Current
                      </span>
                    ) : null}
                  </button>
                </li>
              );
            })}
          </ul>
        )}
      </div>
    </LemonModal>
  );
}
