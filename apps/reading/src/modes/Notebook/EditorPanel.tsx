import { NotebookEditor, normalizeNotebookId } from "./Editor";

/**
 * EditorPanel — panel-friendly wrapper around the new TipTap-based
 * NotebookEditor. Registered in PanelRegistry under
 * `PanelKind = "NotebookEditor"`; opened via workspace actions.
 *
 * Props arrive from the workspace open() call (the panel's stored
 * props are spread into the renderer). Required:
 *   - notebookId: string  (stable id for substrate autosave + local mirror)
 *
 * Optional:
 *   - placeholder: string
 *   - initialContent: string (HTML)
 */
type Props = {
  notebookId?: string | null;
  placeholder?: string;
  initialContent?: string;
};

export default function EditorPanel({
  notebookId,
  placeholder,
  initialContent,
}: Props) {
  const id = normalizeNotebookId(notebookId);
  return (
    <NotebookEditor
      notebookId={id}
      placeholder={placeholder}
      initialContent={initialContent}
      className="h-full"
    />
  );
}
