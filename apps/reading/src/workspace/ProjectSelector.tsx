import { useEffect, useLayoutEffect, useRef, useState, useSyncExternalStore } from "react";
import { useLocation, useNavigate, useNavigationType } from "react-router-dom";
import { createProject, listProjects, type Project } from "../lib/api/projects";
import { getTabOwner, subscribeTabOwner } from "./tabTreeOwner";
import { useTabTrees } from "./tabTreeStore";
import { mothershipForPath, MODE_HOME } from "./mothershipForPath";
import { routeForTab, routeTabFor } from "./documentSpace";
import { PROJECT_PARAM, projectFromSearch, retryProjectSelection, useProjectSelection, withProject } from "./projectSelection";
import { setCompanionMode } from "./companionTreeBinding";

export default function ProjectSelector() {
  const location = useLocation();
  const navigate = useNavigate();
  const navigationType = useNavigationType();
  const owner = useSyncExternalStore(subscribeTabOwner, getTabOwner);
  const selectedId = projectFromSearch(location.search);
  const mode = mothershipForPath(location.pathname, location.search);
  const selection = useProjectSelection();
  const contextEpoch = useTabTrees((state) => state.contextEpoch);
  const [projects, setProjects] = useState<Project[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [creating, setCreating] = useState(false);
  const [showCreate, setShowCreate] = useState(false);
  const [title, setTitle] = useState("");
  const explicitSession = useRef(false);
  const previous = useRef(selectedId);
  const latestLocation = useRef(location);
  useLayoutEffect(() => { latestLocation.current = location; }, [location]);
  const requestSequence = useRef(0);

  useEffect(() => { setCreating(false); setTitle(""); }, [owner.epoch]);

  // Mode doors and older route callers keep the project even if they omit
  // the query. Back/forward and an explicit Session choice retain URL authority.
  useEffect(() => {
    if (!selectedId && previous.current && navigationType !== "POP" && !explicitSession.current) {
      navigate(withProject(location.pathname + location.search + location.hash, previous.current), { replace: true });
      return;
    }
    previous.current = selectedId;
    explicitSession.current = false;
  }, [selectedId, navigationType, location, navigate]);

  useEffect(() => {
    setCompanionMode(mode);
    if (selection.status === "ready") void useTabTrees.getState().ensureMothership(mode);
  }, [mode, selection.status]);

  useEffect(() => {
    if (!selectedId && previous.current && navigationType !== "POP" && !explicitSession.current) return;
    const sequence = ++requestSequence.current;
    const controller = new AbortController();
    let cancelled = false;
    const epoch = owner.epoch;
    const current = () => sequence === requestSequence.current && !controller.signal.aborted && getTabOwner().epoch === epoch && !getTabOwner().suspended;
    const state = useTabTrees.getState();
    const switching = state.projectId !== selectedId;
    // A selection never files old session/project nodes into a new owner row.
    if (switching) state.resetTabTrees();
    useProjectSelection.setState({ requestedId: selectedId, status: "loading" });
    setProjects([]);
    setError(null);
    if (!owner.owner || owner.suspended) {
      useProjectSelection.setState({ requestedId: selectedId, status: "unavailable" });
      return () => { cancelled = true; controller.abort(); };
    }
    void (async () => {
      try {
        const rows = await listProjects({ signal: controller.signal });
        if (cancelled) return;
        if (!current()) return;
        setProjects(rows.filter((project) => project.archived_at === null));
        if (selectedId && !rows.some((project) => project.project_id === selectedId && project.archived_at === null)) {
          useProjectSelection.setState({ requestedId: selectedId, status: "missing" });
          setError("This project is unavailable for this account. Choose a project.");
          return;
        }
        await useTabTrees.getState().bindActiveProject(async () => selectedId);
        if (cancelled) return;
        if (!current()) return;
        const route = latestLocation.current;
        const m = mothershipForPath(route.pathname, route.search);
        setCompanionMode(m);
        await useTabTrees.getState().ensureMothership(m);
        if (cancelled) return;
        if (!current()) return;
        // Only an explicit project switch lands on that project's saved
        // document. Initial deep links remain the operator's navigation.
        if (switching && selectedId && route.pathname === MODE_HOME[m]) {
          const tree = useTabTrees.getState().trees[m];
          const holder = tree?.active_left ? routeTabFor(tree, tree.active_left) : null;
          const target = holder ? routeForTab(holder) : null;
          if (target) navigate(withProject(target, selectedId), { replace: true });
        }
        useProjectSelection.setState({ requestedId: selectedId, status: "ready" });
      } catch {
        if (cancelled) return;
        if (!current()) return;
        useProjectSelection.setState({ requestedId: selectedId, status: "unavailable" });
        setError("Projects could not be loaded. Tabs stay in this session.");
      }
    })();
    return () => { cancelled = true; controller.abort(); };
    // The URL identity and authenticated owner control the binding; route
    // changes are read from latestLocation without restarting owner lookups.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [selectedId, owner.epoch, owner.suspended, selection.retry]);

  useEffect(() => {
    if (selectedId && useProjectSelection.getState().status === "ready" && useTabTrees.getState().projectId !== selectedId) retryProjectSelection();
  }, [contextEpoch, selectedId]);

  function select(projectId: string) {
    explicitSession.current = !projectId;
    previous.current = projectId || null;
    const params = new URLSearchParams();
    if (projectId) params.set(PROJECT_PARAM, projectId);
    navigate(`${MODE_HOME[mode]}${params.size ? `?${params}` : ""}`);
  }

  async function create() {
    const name = title.trim();
    if (!name || creating || !owner.owner || owner.suspended) return;
    const epoch = owner.epoch;
    const sequence = requestSequence.current;
    setCreating(true);
    try {
      const project = await createProject({ title: name });
      if (getTabOwner().epoch !== epoch || requestSequence.current !== sequence || getTabOwner().suspended) return;
      setTitle("");
      setShowCreate(false);
      select(project.project_id);
    } catch {
      if (getTabOwner().epoch === epoch && requestSequence.current === sequence) setError("Project creation failed. Your title is kept so you can try again.");
    } finally {
      if (getTabOwner().epoch === epoch) setCreating(false);
    }
  }

  return (
    <div className="relative flex items-center gap-1 text-xs">
      <select aria-label="Selected project" value={selectedId ?? ""} onChange={(event) => select(event.target.value)} disabled={!owner.owner || owner.suspended} className="max-w-44 bg-card text-1 border border-hairline rounded px-1 py-1">
        <option value="">Session only</option>
        {selectedId && !projects.some((project) => project.project_id === selectedId) && <option value={selectedId}>Project unavailable</option>}
        {projects.map((project) => <option key={project.project_id} value={project.project_id}>{project.title}</option>)}
      </select>
      <button type="button" aria-label="Create project" onClick={() => setShowCreate((open) => !open)} disabled={!owner.owner || owner.suspended} className="px-1 py-1 text-2 hover:text-1">+</button>
      {showCreate && <form onSubmit={(event) => { event.preventDefault(); void create(); }} className="absolute z-30 top-full right-0 mt-1 p-2 bg-card border border-hairline rounded shadow-lg flex gap-1">
        <input aria-label="Project title" value={title} onChange={(event) => setTitle(event.target.value)} maxLength={200} className="bg-inset text-1 rounded px-2 py-1" />
        <button type="submit" disabled={creating || !title.trim()} className="px-2 text-1">{creating ? "Creating…" : "Create"}</button>
      </form>}
      {error && <span role="status" className="absolute z-20 top-full right-0 mt-1 w-64 bg-card border border-hairline rounded p-2 text-2">{error}<button type="button" onClick={retryProjectSelection} className="ml-1 underline">Retry projects</button></span>}
    </div>
  );
}
