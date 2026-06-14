/**
 * Site-wide ambient background — slow-shifting gradient mesh inspired by
 * premium automation/AI landing pages (radial glows + animated gradient sweep).
 */
export function AnimatedBackground() {
  return (
    <div
      aria-hidden
      className="ambient-bg pointer-events-none fixed inset-0 -z-10 overflow-hidden"
    >
      <div className="ambient-bg-mesh absolute inset-0" />
      <div className="ambient-bg-shift absolute inset-0" />
      <div className="ambient-bg-grid absolute inset-0" />
      <div className="ambient-bg-vignette absolute inset-0" />
    </div>
  );
}
