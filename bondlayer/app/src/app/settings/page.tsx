"use client";

import { useSelectedMerchant } from "@/lib/api";

export default function SettingsPage() {
  const merchant = useSelectedMerchant();
  const endpoints = merchant
    ? [
        ["UCP profile", `/${merchant}/.well-known/ucp`],
        ["Catalogue search", `/${merchant}/ucp/catalog/search`],
        ["Readiness report", `/onboard/report/${merchant}`],
      ]
    : [];

  return (
    <div className="content">
      <div className="page-heading">
        <div><h1>Settings</h1><p>The agent-facing endpoints this server publishes for the selected merchant.</p></div>
      </div>

      <div className="settings-grid">
        <section className="panel">
          <div className="panel-heading">
            <div><h2>Agent access</h2><p>Served by this process; open one to see the live response</p></div>
          </div>
          <div className="setting-list">
            {merchant === null && <p>Select a merchant to see its endpoints.</p>}
            {endpoints.map(([label, path]) => (
              <label key={path}>
                <span>{label}</span>
                <a href={path}>{path}</a>
              </label>
            ))}
          </div>
        </section>
        <section className="panel">
          <div className="panel-heading">
            <div><h2>Merchant profile</h2><p>Editing merchant settings</p></div>
            <span className="pill neutral">Not in this prototype</span>
          </div>
        </section>
      </div>
    </div>
  );
}
