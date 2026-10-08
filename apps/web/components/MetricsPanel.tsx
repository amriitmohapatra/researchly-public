import type { Metrics } from "@researchly/contract";
import { sectionLabel } from "@/lib/categories";

const n0 = new Intl.NumberFormat("en-GB", { maximumFractionDigits: 0 });
const n1 = new Intl.NumberFormat("en-GB", { maximumFractionDigits: 1 });
const pct = new Intl.NumberFormat("en-GB", { style: "percent", maximumFractionDigits: 0 });

/** Read-outs describe the text. There is deliberately no score, grade or target. */
export function MetricsPanel({ metrics }: { metrics: Metrics }) {
  const passive = Object.entries(metrics.passive_share_by_section ?? {});
  const rows: { term: string; value: string; note?: string }[] = [
    { term: "Words", value: n0.format(metrics.words) },
    { term: "Sentences", value: n0.format(metrics.sentences) },
    { term: "Mean sentence length", value: `${n1.format(metrics.mean_sentence_len)} words` },
    { term: "Long sentences", value: n0.format(metrics.long_sentences) },
    { term: "Hedges", value: `${n1.format(metrics.hedges_per_100w)} per 100 words`, note: "may, suggest, appear" },
    { term: "Boosters", value: `${n1.format(metrics.boosters_per_100w)} per 100 words`, note: "clearly, demonstrate, prove" },
  ];
  if (metrics.hedge_booster_balance) {
    rows.push({ term: "Hedge to booster balance", value: metrics.hedge_booster_balance });
  }
  rows.push(
    { term: "Nominalisations", value: `${n1.format(metrics.nominalizations_per_100w)} per 100 words` },
    { term: "Self-mentions", value: `${n1.format(metrics.self_mention_per_100w)} per 100 words`, note: "I, we, our" },
  );
  return (
    <section className="panel metrics" aria-labelledby="metrics-heading">
      <h2 id="metrics-heading" className="panel-title">
        Read-outs
      </h2>
      <p className="muted">
        Read-outs, not a score. They describe your text so you can notice patterns; there is no target value.
      </p>
      <dl className="metrics-grid">
        {rows.map((r) => (
          <div key={r.term} className="metric">
            <dt>{r.term}</dt>
            <dd>
              {r.value}
              {r.note ? <span className="metric-note">{r.note}</span> : null}
            </dd>
          </div>
        ))}
        {passive.length > 0 ? (
          <div className="metric metric-wide">
            <dt>Passive voice, by section</dt>
            <dd>
              {passive.map(([sec, share], i) => (
                <span key={sec}>
                  {i > 0 ? " · " : ""}
                  {sectionLabel(sec) ?? "Unlabelled"} {pct.format(share)}
                </span>
              ))}
              <span className="metric-note">Passive voice is expected in Methods.</span>
            </dd>
          </div>
        ) : null}
      </dl>
    </section>
  );
}
