"use client";

/**
 * Loading and failure states. A page that cannot reach the API says so; it
 * never falls back to a placeholder number, because a placeholder that looks
 * like data is the exact failure this console exists to argue against.
 */
export function Loading({ what }: { what: string }) {
  return <p className="state-note">Loading {what}…</p>;
}

export function Failed({ what, error }: { what: string; error: string }) {
  return (
    <div className="state-error" role="alert">
      <strong>Could not load {what}.</strong>
      <p>
        This console reads the merchant server on the same origin. Start it with{" "}
        <code>./run.sh --no-agent</code> and reload.
      </p>
      <code>{error}</code>
    </div>
  );
}
