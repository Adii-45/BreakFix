/** Shimmering placeholders shaped like the content they stand in for. */
export function SkeletonLine({ w = '100%', h = 12, style }) {
  return <div className="sk sk-line" style={{ width: w, height: h, ...style }} />;
}

export function SkeletonChallengeCard() {
  return (
    <div className="card card-pad stack gap-md" aria-hidden="true">
      <div className="row gap-sm">
        <SkeletonLine w="120px" h={12} />
        <span className="spacer" />
        <SkeletonLine w="56px" h={18} />
      </div>
      <SkeletonLine w="65%" h={22} />
      <SkeletonLine w="100%" h={10} />
      <SkeletonLine w="80%" h={10} />
      <div className="row gap-sm" style={{ marginTop: 4 }}>
        <SkeletonLine w="72px" h={22} />
        <SkeletonLine w="60px" h={22} />
        <SkeletonLine w="66px" h={22} />
      </div>
      <div className="sk" style={{ height: 70, borderRadius: 6 }} />
      <div className="row gap-sm">
        <SkeletonLine w="88px" h={12} />
        <span className="spacer" />
        <SkeletonLine w="110px" h={30} />
      </div>
    </div>
  );
}

export function SkeletonRows({ rows = 6, height = 44 }) {
  return (
    <div aria-hidden="true">
      {Array.from({ length: rows }).map((_, i) => (
        <div key={i} className="row gap-md" style={{ height, padding: '0 12px', borderBottom: '1px solid var(--border-subtle)' }}>
          <SkeletonLine w="24px" h={12} />
          <SkeletonLine w="140px" h={12} />
          <span className="spacer" />
          <SkeletonLine w="90px" h={12} />
          <SkeletonLine w="48px" h={12} />
        </div>
      ))}
    </div>
  );
}

export function SkeletonStat() {
  return (
    <div className="stack gap-sm" aria-hidden="true">
      <SkeletonLine w="90px" h={10} />
      <SkeletonLine w="64px" h={24} />
    </div>
  );
}
