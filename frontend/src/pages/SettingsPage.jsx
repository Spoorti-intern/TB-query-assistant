import { Settings } from "lucide-react";

export default function SettingsPage() {
  return (
    <div className="tb-panel">
      <Settings size={25} />
      <h3 style={{ marginTop: 15 }}>Settings</h3>
      <p className="tb-muted">
        Application settings will be added in a later phase.
      </p>
    </div>
  );
}
