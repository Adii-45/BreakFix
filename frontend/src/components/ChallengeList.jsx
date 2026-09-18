export default function ChallengeList({ challenges, onSelect, startingId, disabled }) {
  if (challenges.length === 0) {
    return <p className="empty">No challenges are seeded yet. Run the authoring pipeline in seed-data/.</p>;
  }
  return (
    <div className="card-grid">
      {challenges.map((challenge) => {
        const starting = startingId === challenge.challenge_id;
        return (
          <button
            key={challenge.challenge_id}
            type="button"
            className="challenge-card"
            disabled={disabled}
            onClick={() => onSelect(challenge)}
            aria-label={`Start ${challenge.function_name} from ${challenge.repo_name}`}
          >
            <span className="repo">{challenge.repo_name}</span>
            <span className="fn">{challenge.function_name}()</span>
            <span className="meta">
              <span className="pill pill-accent">{challenge.difficulty}</span>
              <span className="pill">{challenge.language}</span>
              <span className="pill">{Math.round((challenge.time_limit_seconds || 300) / 60)} min</span>
            </span>
            <span className="cta">{starting ? 'Starting…' : 'Start challenge →'}</span>
          </button>
        );
      })}
    </div>
  );
}
