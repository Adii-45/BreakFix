/** Line diff (LCS) for the "Your change" panel. Returns only the changed lines
 *  plus `context` neighbours, or null when the inputs are too large to diff. */
export function lineDiff(before, after, context = 1) {
  const a = String(before).replace(/\r\n/g, '\n').split('\n');
  const b = String(after).replace(/\r\n/g, '\n').split('\n');
  const n = a.length;
  const m = b.length;
  if (n * m > 400000) return null;

  const same = (i, j) => a[i].trimEnd() === b[j].trimEnd();
  const dp = Array.from({ length: n + 1 }, () => new Uint16Array(m + 1));
  for (let i = n - 1; i >= 0; i -= 1) {
    for (let j = m - 1; j >= 0; j -= 1) {
      dp[i][j] = same(i, j) ? dp[i + 1][j + 1] + 1 : Math.max(dp[i + 1][j], dp[i][j + 1]);
    }
  }

  const ops = [];
  let i = 0;
  let j = 0;
  while (i < n && j < m) {
    if (same(i, j)) { ops.push({ t: 'ctx', text: b[j], ln: j + 1 }); i += 1; j += 1; }
    else if (dp[i + 1][j] >= dp[i][j + 1]) { ops.push({ t: 'del', text: a[i], ln: i + 1 }); i += 1; }
    else { ops.push({ t: 'add', text: b[j], ln: j + 1 }); j += 1; }
  }
  while (i < n) { ops.push({ t: 'del', text: a[i], ln: i + 1 }); i += 1; }
  while (j < m) { ops.push({ t: 'add', text: b[j], ln: j + 1 }); j += 1; }

  const keep = new Array(ops.length).fill(false);
  ops.forEach((op, k) => {
    if (op.t === 'ctx') return;
    for (let d = -context; d <= context; d += 1) if (ops[k + d]) keep[k + d] = true;
  });
  return ops.filter((_, k) => keep[k]);
}
