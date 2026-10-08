import type { TierHealth } from "@researchly/contract";
import { healthBanners } from "@/lib/health";

/** A degraded tier is reported, never hidden (CLAUDE.md) — but calmly: the rest of the check still ran. */
export function HealthBanner({ health }: { health: readonly TierHealth[] }) {
  const banners = healthBanners(health);
  if (banners.length === 0) return null;
  return (
    <div className="notice notice-health" role="status" data-testid="health-banner">
      <svg width="18" height="18" viewBox="0 0 16 16" aria-hidden="true" focusable="false" className="notice-icon">
        <circle cx="8" cy="8" r="6.5" fill="none" stroke="currentColor" strokeWidth="1.4" />
        <path d="M8 7v4.2" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" />
        <circle cx="8" cy="4.8" r="0.95" fill="currentColor" />
      </svg>
      <div>
        {banners.map((b) => (
          <div key={b.tier} className="notice-item">
            <p className="notice-title">{b.title}</p>
            {b.detail ? <p className="notice-text">{b.detail}.</p> : null}
            {b.remedy ? (
              <p className="notice-text">
                <span className="notice-label">Remedy:</span> {b.remedy}
              </p>
            ) : null}
          </div>
        ))}
        <p className="notice-text notice-foot">
          The other checks ran normally. Only suggestions from the unavailable checks are missing.
        </p>
      </div>
    </div>
  );
}
