import { formatRate, sparkPoints } from "@/lib/progress-view";

const W = 132;
const H = 36;

/**
 * One rule's line (S4c progress): flags per 1,000 words in each recorded
 * check, oldest on the left, from zero at the bottom to the line's own
 * highest value. One series, one hue (the accent), a 2px line, a hairline
 * baseline, and an end dot with a surface ring marking the latest check.
 * Every point has a hit area larger than the mark with its value as a
 * native tooltip; the same values are written out in the page's table, so
 * nothing depends on hovering. Decorative to assistive technology beyond
 * its one-sentence label: the numbers beside it carry the reading.
 */
export function Sparkline({ rates, label }: { rates: readonly number[]; label: string }) {
  const pts = sparkPoints(rates, W, H);
  const last = pts[pts.length - 1];
  const path = pts.map((p, i) => `${i === 0 ? "M" : "L"}${p.x.toFixed(1)} ${p.y.toFixed(1)}`).join(" ");
  return (
    <svg className="spark" width={W} height={H} viewBox={`0 0 ${W} ${H}`} role="img" aria-label={label} data-testid="sparkline">
      <line className="spark-base" x1={0} x2={W} y1={H - 4} y2={H - 4} />
      {pts.length > 1 ? <path className="spark-line" d={path} /> : null}
      {pts.map((p, i) => (
        <circle key={i} className="spark-hit" cx={p.x} cy={p.y} r={8}>
          <title>{`Check ${i + 1}: ${formatRate(rates[i] ?? 0)} per 1,000 words`}</title>
        </circle>
      ))}
      {last ? <circle className="spark-end" cx={last.x} cy={last.y} r={4} /> : null}
    </svg>
  );
}
