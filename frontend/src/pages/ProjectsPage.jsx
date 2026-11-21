import { FolderKanban } from "lucide-react";

export default function ProjectsPage() {
  return (
    <>
      <div className="tb-page-heading">
        <div>
          <h1>Projects</h1>
          <p className="tb-muted">Organize your database query work.</p>
        </div>
      </div>

      <div className="tb-panel">
        <FolderKanban size={25} />
        <h3 style={{ marginTop: 15 }}>Your projects</h3>
        <p className="tb-muted">
          Project creation and management will be added in a later development phase.
        </p>
      </div>
    </>
  );
}
